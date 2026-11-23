import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from httpx import AsyncClient, ASGITransport
from app.main import app


async def test_auth_and_rbac():
    print("🧪 Running Phase 0 Verification Tests...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res = await client.get("/health")
        assert res.status_code == 200, f"Health check failed: {res.text}"
        print("  ✓ Health check passed")

        # 2. Login as Owner
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@omnisuite.io", "password": "Password@123"},
        )
        assert login_res.status_code == 200, f"Owner login failed: {login_res.text}"
        owner_data = login_res.json()
        owner_token = owner_data["access_token"]
        assert owner_data["user"]["role"]["slug"] == "owner"
        print(f"  ✓ Owner login succeeded: {owner_data['user']['full_name']}")

        # 3. Check /me endpoint
        me_res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert me_res.status_code == 200
        print(f"  ✓ /auth/me verified for: {me_res.json()['email']}")

        # 4. Check branches for Owner (sees both branches)
        branches_res = await client.get(
            "/api/v1/auth/branches",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert branches_res.status_code == 200
        branches = branches_res.json()
        assert len(branches) == 2, f"Expected 2 branches, got {len(branches)}"
        print(f"  ✓ Owner sees all {len(branches)} branches")

        # 5. Login as Technician
        tech_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "tech@omnisuite.io", "password": "Password@123"},
        )
        assert tech_res.status_code == 200
        tech_token = tech_res.json()["access_token"]
        print(f"  ✓ Technician login succeeded: {tech_res.json()['user']['full_name']}")

        # 6. Branch scoping for Technician (should only see assigned branch)
        tech_branches = await client.get(
            "/api/v1/auth/branches",
            headers={"Authorization": f"Bearer {tech_token}"},
        )
        assert tech_branches.status_code == 200
        assert len(tech_branches.json()) == 1
        print("  ✓ Technician branch strictly scoped to 1 branch")

        # 7. Check audit logs endpoint with Owner (has settings permission)
        audit_res = await client.get(
            "/api/v1/audit-logs",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert audit_res.status_code == 200, f"Audit logs query failed: {audit_res.text}"
        audit_data = audit_res.json()
        print(f"  ✓ Audit logs retrieved: {audit_data['total']} events recorded")
        assert audit_data["total"] >= 2, "Expected login audit events recorded"

        # 8. Check audit logs endpoint with Technician (technician has NONE for settings) -> Expect 403 Forbidden
        tech_audit_res = await client.get(
            "/api/v1/audit-logs",
            headers={"Authorization": f"Bearer {tech_token}"},
        )
        assert tech_audit_res.status_code == 403, f"Expected 403 for technician, got {tech_audit_res.status_code}"
        print("  ✓ RBAC enforced: Technician correctly forbidden (403) from accessing audit logs / settings")

    print("🎉 All Phase 0 backend verification tests passed successfully!")


if __name__ == "__main__":
    asyncio.run(test_auth_and_rbac())
