from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.custom_field import CustomFieldDefinition
from app.models.pipeline import StatusPipeline, StatusDefinition, StatusTransition
from app.models.handbook import Handbook, HandbookItem
from app.models.template import DocumentTemplate
from app.models.base import generate_uuid
from app.services.preset_data import INDUSTRY_PRESETS


async def apply_industry_preset(
    db: AsyncSession,
    preset_key: str,
    branch_id: Optional[str] = None,
    override_existing: bool = False,
) -> Dict[str, Any]:
    if preset_key not in INDUSTRY_PRESETS:
        raise ValueError(f"Unknown preset key: '{preset_key}'. Available: {list(INDUSTRY_PRESETS.keys())}")

    preset = INDUSTRY_PRESETS[preset_key]
    cf_count = 0
    pipe_count = 0
    status_count = 0
    trans_count = 0
    hb_count = 0
    hb_item_count = 0
    tmpl_count = 0

    # 1. Seed Custom Fields
    for f in preset.get("custom_fields", []):
        # Check if already exists for this entity & key & branch
        stmt = select(CustomFieldDefinition).where(
            CustomFieldDefinition.entity == f["entity"],
            CustomFieldDefinition.field_key == f["field_key"],
            CustomFieldDefinition.branch_id == branch_id,
        )
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

        if not existing:
            cf = CustomFieldDefinition(
                id=generate_uuid(),
                branch_id=branch_id,
                entity=f["entity"],
                field_key=f["field_key"],
                name=f["name"],
                field_type=f["field_type"],
                required=f.get("required", False),
                unique=f.get("unique", False),
                placeholder=f.get("placeholder"),
                default_value=f.get("default_value"),
                options=f.get("options", []),
                formula_expression=f.get("formula_expression"),
                role_visibility=f.get("role_visibility", []),
                conditional_display=f.get("conditional_display"),
                sort_order=f.get("sort_order", 0),
                is_active=True,
            )
            db.add(cf)
            cf_count += 1

    # 2. Seed Pipeline, Statuses & Transitions
    pipe_data = preset.get("pipeline")
    if pipe_data:
        # Check if pipeline with this code exists
        p_stmt = select(StatusPipeline).where(
            StatusPipeline.code == pipe_data["code"],
            StatusPipeline.branch_id == branch_id,
        )
        p_res = await db.execute(p_stmt)
        existing_pipe = p_res.scalar_one_or_none()

        if not existing_pipe or override_existing:
            if existing_pipe and override_existing:
                await db.delete(existing_pipe)
                await db.flush()

            pipeline = StatusPipeline(
                id=generate_uuid(),
                branch_id=branch_id,
                entity=pipe_data.get("entity", "ticket"),
                name=pipe_data["name"],
                code=pipe_data["code"],
                description=pipe_data.get("description"),
                is_default=True,
                is_active=True,
            )
            db.add(pipeline)
            await db.flush()
            pipe_count += 1

            # Seed Status Definitions
            status_map: Dict[str, str] = {}
            for s in pipe_data.get("statuses", []):
                status_id = generate_uuid()
                status_def = StatusDefinition(
                    id=status_id,
                    pipeline_id=pipeline.id,
                    name=s["name"],
                    code=s["code"],
                    bg_color=s.get("bg_color", "#f1f5f9"),
                    text_color=s.get("text_color", "#0f172a"),
                    icon=s.get("icon", "circle"),
                    sort_order=s.get("sort_order", 0),
                    is_initial=s.get("is_initial", False),
                    is_terminal=s.get("is_terminal", False),
                    is_active=True,
                )
                db.add(status_def)
                status_map[s["code"]] = status_id
                status_count += 1

            await db.flush()

            # Seed Transitions
            for t in pipe_data.get("transitions", []):
                from_id = status_map.get(t["from_code"])
                to_id = status_map.get(t["to_code"])
                if from_id and to_id:
                    trans = StatusTransition(
                        id=generate_uuid(),
                        pipeline_id=pipeline.id,
                        from_status_id=from_id,
                        to_status_id=to_id,
                        name=t.get("name"),
                        guards=t.get("guards", {}),
                        event_hooks=t.get("event_hooks", {}),
                        is_active=True,
                    )
                    db.add(trans)
                    trans_count += 1

    # 3. Seed Handbooks and HandbookItems
    for hb_data in preset.get("handbooks", []):
        h_stmt = select(Handbook).where(
            Handbook.code == hb_data["code"],
            Handbook.branch_id == branch_id,
        )
        h_res = await db.execute(h_stmt)
        existing_hb = h_res.scalar_one_or_none()

        if not existing_hb or override_existing:
            if existing_hb and override_existing:
                await db.delete(existing_hb)
                await db.flush()

            handbook = Handbook(
                id=generate_uuid(),
                branch_id=branch_id,
                code=hb_data["code"],
                name=hb_data["name"],
                description=hb_data.get("description"),
                is_hierarchical=hb_data.get("is_hierarchical", False),
                is_system=True,
                is_active=True,
            )
            db.add(handbook)
            await db.flush()
            hb_count += 1

            async def insert_items(items: List[Dict[str, Any]], parent_id: Optional[str] = None):
                nonlocal hb_item_count
                for idx, item in enumerate(items):
                    item_id = generate_uuid()
                    hb_item = HandbookItem(
                        id=item_id,
                        handbook_id=handbook.id,
                        parent_id=parent_id,
                        code=item["code"],
                        name=item["name"],
                        sort_order=idx + 1,
                        is_active=True,
                        extra_data=item.get("extra_data", {}),
                    )
                    db.add(hb_item)
                    hb_item_count += 1
                    if "children" in item and item["children"]:
                        await insert_items(item["children"], parent_id=item_id)

            await insert_items(hb_data.get("items", []))

    # 4. Seed Document Templates
    for t_data in preset.get("templates", []):
        t_stmt = select(DocumentTemplate).where(
            DocumentTemplate.name == t_data["name"],
            DocumentTemplate.branch_id == branch_id,
        )
        t_res = await db.execute(t_stmt)
        existing_tmpl = t_res.scalar_one_or_none()

        if not existing_tmpl or override_existing:
            if existing_tmpl and override_existing:
                await db.delete(existing_tmpl)
                await db.flush()

            tmpl = DocumentTemplate(
                id=generate_uuid(),
                branch_id=branch_id,
                type=t_data["type"],
                name=t_data["name"],
                paper_width=t_data.get("paper_width", "80mm"),
                html_body=t_data["html_body"],
                variables=t_data.get("variables", []),
                is_default=True,
                is_active=True,
            )
            db.add(tmpl)
            tmpl_count += 1

    await db.commit()

    return {
        "success": True,
        "preset_key": preset_key,
        "preset_name": preset["name"],
        "custom_fields_created": cf_count,
        "pipelines_created": pipe_count,
        "statuses_created": status_count,
        "transitions_created": trans_count,
        "handbooks_created": hb_count,
        "handbook_items_created": hb_item_count,
        "templates_created": tmpl_count,
        "message": f"Successfully applied '{preset['name']}' preset with {cf_count} custom fields, {status_count} pipeline statuses, {trans_count} transitions, {hb_item_count} handbook entries, and {tmpl_count} document templates.",
    }
