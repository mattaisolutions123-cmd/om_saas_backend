import pytest
from app.services.gst_service import GSTService


class TestGSTEngine:
    def test_intra_state_gst_split(self):
        """
        Verify intra-state supply (same state e.g., Maharashtra 27 to Maharashtra 27):
        CGST = 50% of GST rate, SGST = 50% of GST rate, IGST = 0%.
        """
        res = GSTService.evaluate_place_of_supply(
            branch_state_code="27",
            customer_state_code="27",
            gst_rate=18.0,
            taxable_amount=10000.0,
        )

        assert res["is_interstate"] is False
        assert res["cgst_rate"] == 9.0
        assert res["cgst_amount"] == 900.0
        assert res["sgst_rate"] == 9.0
        assert res["sgst_amount"] == 900.0
        assert res["igst_rate"] == 0.0
        assert res["igst_amount"] == 0.0
        assert res["total_tax"] == 1800.0
        assert res["total_amount"] == 11800.0

    def test_inter_state_gst_split(self):
        """
        Verify inter-state supply (e.g., Maharashtra 27 to Karnataka 29):
        CGST = 0%, SGST = 0%, IGST = 100% of GST rate.
        """
        res = GSTService.evaluate_place_of_supply(
            branch_state_code="27",
            customer_state_code="29",
            gst_rate=18.0,
            taxable_amount=10000.0,
        )

        assert res["is_interstate"] is True
        assert res["cgst_rate"] == 0.0
        assert res["cgst_amount"] == 0.0
        assert res["sgst_rate"] == 0.0
        assert res["sgst_amount"] == 0.0
        assert res["igst_rate"] == 18.0
        assert res["igst_amount"] == 1800.0
        assert res["total_tax"] == 1800.0
        assert res["total_amount"] == 11800.0

    def test_multiple_gst_slab_rates(self):
        """
        Verify standard Indian GST slab rates (5%, 12%, 18%, 28%).
        """
        slabs = [
            (5.0, 1000.0, 25.0, 25.0, 50.0),
            (12.0, 2000.0, 120.0, 120.0, 240.0),
            (18.0, 5000.0, 450.0, 450.0, 900.0),
            (28.0, 10000.0, 1400.0, 1400.0, 2800.0),
        ]

        for rate, taxable, exp_cgst, exp_sgst, exp_tax in slabs:
            res = GSTService.evaluate_place_of_supply(
                branch_state_code="27",
                customer_state_code="27",
                gst_rate=rate,
                taxable_amount=taxable,
            )
            assert res["cgst_amount"] == exp_cgst
            assert res["sgst_amount"] == exp_sgst
            assert res["total_tax"] == exp_tax
            assert res["total_amount"] == taxable + exp_tax

    def test_exempt_zero_rate(self):
        """
        Verify 0% exempt supply.
        """
        res = GSTService.evaluate_place_of_supply(
            branch_state_code="27",
            customer_state_code="27",
            gst_rate=0.0,
            taxable_amount=1500.0,
        )
        assert res["cgst_amount"] == 0.0
        assert res["sgst_amount"] == 0.0
        assert res["total_tax"] == 0.0
        assert res["total_amount"] == 1500.0

    def test_irn_hash_generation(self):
        """
        Verify 64-character SHA-256 Invoice Reference Number (IRN) format.
        """
        irn = GSTService.generate_irn_hash(
            supplier_gstin="27AAFCO1234F1Z5",
            doc_type="INV",
            doc_num="INV-202611-0001",
            doc_date="2026-11-23",
        )
        assert isinstance(irn, str)
        assert len(irn) == 64
        # Verify hex characters only
        assert all(c in "0123456789abcdef" for c in irn)
