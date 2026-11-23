import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.custom_field import CustomFieldDefinition
from app.models.pipeline import StatusPipeline, StatusDefinition, StatusTransition
from app.models.handbook import Handbook, HandbookItem
from app.models.template import DocumentTemplate
from app.models.branch import Branch
from app.models.user import User
from app.models.rbac import Role
from app.services.preset_data import INDUSTRY_PRESETS
from app.services.preset_seeder import apply_industry_preset
from app.schemas.pipeline import TransitionValidateRequest
from app.api.v1.settings.pipelines import validate_transition
from app.api.v1.settings.templates import render_preview
from app.schemas.template import DocumentTemplateRenderRequest


async def run_phase1_tests():
    print("🧪 Running Phase 1 Zero-Code Settings Engine Backend Tests...", flush=True)

    async with AsyncSessionLocal() as db:
        # 1. Verify 4 Industry Presets Seeding
        print("\n--- 1. Testing Industry Presets Seeder ---")
        for pkey in ["appliance_motor", "automotive_garage", "mobile_it_repair", "hvac_tailoring"]:
            res = await apply_industry_preset(db, pkey, branch_id=None, override_existing=True)
            assert res["success"] is True
            print(f"  ✓ Seeded preset '{pkey}': {res['custom_fields_created']} fields, {res['statuses_created']} statuses, {res['handbook_items_created']} handbook items")

        # 2. Verify 12 Custom Field Types
        print("\n--- 2. Testing 12 Custom Field Types ---")
        cf_res = await db.execute(select(CustomFieldDefinition))
        fields = cf_res.scalars().all()
        field_types = {f.field_type for f in fields}
        expected_types = {
            "short_text", "long_text", "number", "dropdown", "multi_select",
            "date_time", "currency", "checkbox", "image_upload", "signature_pad",
            "barcode_scan", "formula"
        }
        for et in expected_types:
            assert et in field_types, f"Missing field type in seeded fields: {et}"
            matching = [f for f in fields if f.field_type == et]
            print(f"  ✓ Field type '{et}' verified (sample: '{matching[0].name}')")

        # Verify formula field and conditional display
        formula_f = next(f for f in fields if f.field_type == "formula")
        assert formula_f.formula_expression is not None
        assert "copper_weight_kg" in formula_f.formula_expression.get("depends_on", [])
        print(f"  ✓ Formula expression verified: {formula_f.formula_expression['expression']}")

        # 3. Verify Status Pipelines, Definitions & Transitions
        print("\n--- 3. Testing Pipelines, Statuses & Transitions ---")
        pipe_res = await db.execute(select(StatusPipeline).where(StatusPipeline.code == "mobile_it_pipeline"))
        mobile_pipe = pipe_res.scalar_one()
        assert mobile_pipe is not None
        print(f"  ✓ Found pipeline: {mobile_pipe.name}")

        status_res = await db.execute(select(StatusDefinition).where(StatusDefinition.pipeline_id == mobile_pipe.id))
        statuses = {s.code: s for s in status_res.scalars().all()}
        assert "intake" in statuses
        assert "delivered" in statuses
        assert statuses["intake"].is_initial is True
        assert statuses["delivered"].is_terminal is True
        print(f"  ✓ Verified initial status: '{statuses['intake'].name}' and terminal status: '{statuses['delivered'].name}'")

        # 4. Verify Closure Gate Guard
        print("\n--- 4. Testing Closure Gate Guard ---")
        trans_res = await db.execute(
            select(StatusTransition).where(
                StatusTransition.pipeline_id == mobile_pipe.id,
                StatusTransition.to_status_id == statuses["delivered"].id,
            )
        )
        delivered_trans = trans_res.scalar_one_or_none()
        assert delivered_trans is not None
        assert delivered_trans.guards.get("closure_gate") is True
        print(f"  ✓ Found transition with closure_gate=True to '{statuses['delivered'].name}'")

        # Test A: Blocked when balance > 0 and no manager override
        technician_user = (await db.execute(select(User).where(User.email == "tech@omnisuite.io"))).scalar_one()
        manager_user = (await db.execute(select(User).where(User.email == "manager@omnisuite.io"))).scalar_one()

        req_blocked = TransitionValidateRequest(
            pipeline_id=mobile_pipe.id,
            from_status_id=delivered_trans.from_status_id,
            to_status_id=delivered_trans.to_status_id,
            current_balance=1500.0,
            manager_override=False,
            actor_role="technician",
        )
        val_blocked = await validate_transition(req_blocked, db=db, current_user=technician_user)
        assert val_blocked.allowed is False
        assert any("Closure Gate Blocked" in r for r in val_blocked.reasons)
        print("  ✓ Correctly BLOCKED transition to Delivered with balance ₹1500.00 and no override")

        # Test B: Allowed when balance is 0.00
        req_zero_balance = TransitionValidateRequest(
            pipeline_id=mobile_pipe.id,
            from_status_id=delivered_trans.from_status_id,
            to_status_id=delivered_trans.to_status_id,
            current_balance=0.0,
            manager_override=False,
            actor_role="technician",
        )
        val_allowed_zero = await validate_transition(req_zero_balance, db=db, current_user=technician_user)
        assert val_allowed_zero.allowed is True
        print("  ✓ Correctly ALLOWED transition to Delivered when balance = ₹0.00")

        # Test C: Allowed when balance > 0 WITH Manager Override by Manager
        req_override = TransitionValidateRequest(
            pipeline_id=mobile_pipe.id,
            from_status_id=delivered_trans.from_status_id,
            to_status_id=delivered_trans.to_status_id,
            current_balance=1500.0,
            manager_override=True,
            actor_role="branch_manager",
        )
        val_allowed_override = await validate_transition(req_override, db=db, current_user=manager_user)
        assert val_allowed_override.allowed is True
        print("  ✓ Correctly ALLOWED transition to Delivered with balance > 0 via Manager Override")

        # 5. Verify Hierarchical Handbooks & Multi-language Labels
        print("\n--- 5. Testing Handbooks & Hierarchical Items ---")
        hb_res = await db.execute(select(Handbook).where(Handbook.code == "brands_models"))
        brand_hb = hb_res.scalar_one()
        assert brand_hb.is_hierarchical is True

        items_res = await db.execute(select(HandbookItem).where(HandbookItem.handbook_id == brand_hb.id))
        all_items = items_res.scalars().all()
        parents = [i for i in all_items if i.parent_id is None]
        children = [i for i in all_items if i.parent_id is not None]
        assert len(parents) > 0
        assert len(children) > 0
        print(f"  ✓ Hierarchical handbook verified: {len(parents)} top brands with {len(children)} model items")

        # Check multi-language labels
        defect_items_res = await db.execute(select(HandbookItem).where(HandbookItem.code == "oled_lines"))
        oled_item = defect_items_res.scalar_one_or_none()
        if oled_item:
            labels = oled_item.extra_data.get("labels", {})
            assert "hi" in labels and "en" in labels
            print(f"  ✓ Multi-language labels verified: English='{labels['en']}', Hindi='{labels['hi']}'")

        # 6. Verify Document Templates & Token Render Engine
        print("\n--- 6. Testing Document Templates & Render Engine ---")
        tmpl_res = await db.execute(select(DocumentTemplate))
        tmpls = tmpl_res.scalars().all()
        widths = {t.paper_width for t in tmpls}
        assert "58mm" in widths or "80mm" in widths
        print(f"  ✓ Found {len(tmpls)} document templates across formats: {widths}")

        # Render preview test
        preview_req = DocumentTemplateRenderRequest(
            template_id=tmpls[0].id,
            context={"customer_name": "Vikram Malhotra", "ticket_number": "TKT-TEST-99"}
        )
        rendered = await render_preview(preview_req, db=db, current_user=manager_user)
        assert "Vikram Malhotra" in rendered.rendered_html
        assert "TKT-TEST-99" in rendered.rendered_html
        print(f"  ✓ Render preview interpolated sample tokens successfully (width: {rendered.paper_width})")

        # 7. Verify Branch Enhancements
        print("\n--- 7. Testing Branch Enhancements ---")
        branch_res = await db.execute(select(Branch))
        branches = branch_res.scalars().all()
        for b in branches:
            assert b.state_code is not None, f"Branch {b.code} missing state_code"
            assert b.currency is not None, f"Branch {b.code} missing currency"
            print(f"  ✓ Branch '{b.name}' ({b.code}): State Code={b.state_code}, Currency={b.currency}, GSTIN={b.gstin}")

    print("\n🎉 ALL PHASE 1 ZERO-CODE SETTINGS ENGINE BACKEND TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(run_phase1_tests())
