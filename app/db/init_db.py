import sqlite3
import sys
from pathlib import Path

# Connect directly to local sqlite and ensure tables exist
db_path = Path(__file__).resolve().parent.parent.parent / "omnisuite.db"
print(f"Initializing database at: {db_path}")

con = sqlite3.connect(str(db_path))
cur = con.cursor()

# 1. Update branches
cur.execute("PRAGMA table_info(branches)")
cols = [row[1] for row in cur.fetchall()]
if "state_code" not in cols:
    cur.execute("ALTER TABLE branches ADD COLUMN state_code VARCHAR(10)")
    print("Added state_code to branches")
if "currency" not in cols:
    cur.execute("ALTER TABLE branches ADD COLUMN currency VARCHAR(10) DEFAULT 'INR' NOT NULL")
    print("Added currency to branches")

# Update existing branches with default currency & state codes
cur.execute("UPDATE branches SET state_code = '27', currency = 'INR' WHERE code = 'BR-MUM-01'")
cur.execute("UPDATE branches SET state_code = '29', currency = 'INR' WHERE code = 'BR-BLR-02'")

# 2. custom_field_definitions
cur.execute("""
CREATE TABLE IF NOT EXISTS custom_field_definitions (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    entity VARCHAR(50) NOT NULL,
    field_key VARCHAR(100) NOT NULL,
    name VARCHAR(150) NOT NULL,
    field_type VARCHAR(50) NOT NULL,
    required BOOLEAN DEFAULT 0 NOT NULL,
    "unique" BOOLEAN DEFAULT 0 NOT NULL,
    placeholder VARCHAR(255),
    default_value JSON,
    options JSON DEFAULT '[]' NOT NULL,
    formula_expression JSON,
    role_visibility JSON DEFAULT '[]' NOT NULL,
    conditional_display JSON,
    sort_order INTEGER DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_cfd_entity ON custom_field_definitions(entity)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_cfd_key ON custom_field_definitions(field_key)")

# 3. status_pipelines
cur.execute("""
CREATE TABLE IF NOT EXISTS status_pipelines (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    entity VARCHAR(50) DEFAULT 'ticket' NOT NULL,
    name VARCHAR(150) NOT NULL,
    code VARCHAR(100) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 4. status_definitions
cur.execute("""
CREATE TABLE IF NOT EXISTS status_definitions (
    id VARCHAR(36) PRIMARY KEY,
    pipeline_id VARCHAR(36) NOT NULL REFERENCES status_pipelines(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(100) NOT NULL,
    bg_color VARCHAR(30) DEFAULT '#f1f5f9' NOT NULL,
    text_color VARCHAR(30) DEFAULT '#0f172a' NOT NULL,
    icon VARCHAR(50) DEFAULT 'circle' NOT NULL,
    sort_order INTEGER DEFAULT 0 NOT NULL,
    is_initial BOOLEAN DEFAULT 0 NOT NULL,
    is_terminal BOOLEAN DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 5. status_transitions
cur.execute("""
CREATE TABLE IF NOT EXISTS status_transitions (
    id VARCHAR(36) PRIMARY KEY,
    pipeline_id VARCHAR(36) NOT NULL REFERENCES status_pipelines(id) ON DELETE CASCADE,
    from_status_id VARCHAR(36) NOT NULL REFERENCES status_definitions(id) ON DELETE CASCADE,
    to_status_id VARCHAR(36) NOT NULL REFERENCES status_definitions(id) ON DELETE CASCADE,
    name VARCHAR(150),
    guards JSON DEFAULT '{}' NOT NULL,
    event_hooks JSON DEFAULT '{}' NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 6. handbooks
cur.execute("""
CREATE TABLE IF NOT EXISTS handbooks (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    is_hierarchical BOOLEAN DEFAULT 0 NOT NULL,
    is_system BOOLEAN DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 7. handbook_items
cur.execute("""
CREATE TABLE IF NOT EXISTS handbook_items (
    id VARCHAR(36) PRIMARY KEY,
    handbook_id VARCHAR(36) NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
    parent_id VARCHAR(36) REFERENCES handbook_items(id) ON DELETE CASCADE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    sort_order INTEGER DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    extra_data JSON DEFAULT '{}' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 8. document_templates
cur.execute("""
CREATE TABLE IF NOT EXISTS document_templates (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    name VARCHAR(150) NOT NULL,
    paper_width VARCHAR(20) DEFAULT '80mm' NOT NULL,
    html_body TEXT NOT NULL,
    variables JSON DEFAULT '[]' NOT NULL,
    is_default BOOLEAN DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 9. clients (Phase 2)
cur.execute("""
CREATE TABLE IF NOT EXISTS clients (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    client_type VARCHAR(20) DEFAULT 'individual' NOT NULL,
    name VARCHAR(200) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    email VARCHAR(100),
    contacts JSON DEFAULT '[]' NOT NULL,
    billing_addresses JSON DEFAULT '[]' NOT NULL,
    gstin VARCHAR(25),
    pan VARCHAR(20),
    credit_limit FLOAT DEFAULT 0.0 NOT NULL,
    credit_period_days FLOAT DEFAULT 0 NOT NULL,
    discount_terms JSON DEFAULT '{}' NOT NULL,
    amc JSON DEFAULT '{}' NOT NULL,
    tags JSON DEFAULT '[]' NOT NULL,
    messaging_opt_in JSON DEFAULT '{"sms": true, "whatsapp": true, "email": true, "promotional": true}' NOT NULL,
    notes TEXT,
    custom_fields JSON DEFAULT '{}' NOT NULL,
    total_spent FLOAT DEFAULT 0.0 NOT NULL,
    outstanding_balance FLOAT DEFAULT 0.0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_clients_phone ON clients(phone)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_clients_name ON clients(name)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_clients_gstin ON clients(gstin)")

# 10. assets (Phase 2)
cur.execute("""
CREATE TABLE IF NOT EXISTS assets (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    brand VARCHAR(100),
    model VARCHAR(100),
    asset_type VARCHAR(50) DEFAULT 'device' NOT NULL,
    identifier VARCHAR(100) NOT NULL,
    dynamic_attributes JSON DEFAULT '{}' NOT NULL,
    warranty_status VARCHAR(30) DEFAULT 'none' NOT NULL,
    warranty_expiry TIMESTAMP,
    purchase_date TIMESTAMP,
    notes TEXT,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_assets_client ON assets(client_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_assets_identifier ON assets(identifier)")

# 11. client_interactions (Phase 2)
cur.execute("""
CREATE TABLE IF NOT EXISTS client_interactions (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    actor_id VARCHAR(36),
    actor_name VARCHAR(150) DEFAULT 'System' NOT NULL,
    actor_role VARCHAR(50),
    type VARCHAR(50) DEFAULT 'note' NOT NULL,
    direction VARCHAR(20) DEFAULT 'internal' NOT NULL,
    title VARCHAR(200) NOT NULL,
    details TEXT,
    extra_metadata JSON DEFAULT '{}' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_interactions_client ON client_interactions(client_id)")

# 12. service_catalog_items (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS service_catalog_items (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(100) DEFAULT 'Repair & Maintenance' NOT NULL,
    sac_code VARCHAR(20) DEFAULT '9987' NOT NULL,
    description TEXT,
    labor_price FLOAT DEFAULT 0.0 NOT NULL,
    duration_minutes INTEGER DEFAULT 60 NOT NULL,
    gst_rate FLOAT DEFAULT 18.0 NOT NULL,
    warranty_days INTEGER DEFAULT 90 NOT NULL,
    commission_rate FLOAT DEFAULT 0.0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_services_name ON service_catalog_items(name)")

# 13. warehouse_locations (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS warehouse_locations (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,
    is_default BOOLEAN DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_warehouse_branch ON warehouse_locations(branch_id)")

# 14. inventory_items (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS inventory_items (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(100) UNIQUE NOT NULL,
    barcode VARCHAR(100) UNIQUE NOT NULL,
    brand VARCHAR(100),
    model_compatibility JSON DEFAULT '[]' NOT NULL,
    category VARCHAR(100) DEFAULT 'General Spare Parts' NOT NULL,
    unit VARCHAR(20) DEFAULT 'PCS' NOT NULL,
    hsn_code VARCHAR(20) DEFAULT '8504' NOT NULL,
    cost_price FLOAT DEFAULT 0.0 NOT NULL,
    retail_price FLOAT DEFAULT 0.0 NOT NULL,
    wholesale_price FLOAT DEFAULT 0.0 NOT NULL,
    min_stock_level FLOAT DEFAULT 5.0 NOT NULL,
    max_stock_level FLOAT DEFAULT 100.0 NOT NULL,
    tax_rate FLOAT DEFAULT 18.0 NOT NULL,
    costing_method VARCHAR(20) DEFAULT 'FIFO' NOT NULL,
    track_inventory BOOLEAN DEFAULT 1 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_inventory_sku ON inventory_items(sku)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_inventory_barcode ON inventory_items(barcode)")

# 15. stock_ledgers (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS stock_ledgers (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    warehouse_location_id VARCHAR(36) REFERENCES warehouse_locations(id) ON DELETE SET NULL,
    movement_type VARCHAR(50) NOT NULL,
    quantity_change FLOAT NOT NULL,
    running_balance FLOAT NOT NULL,
    unit_cost FLOAT DEFAULT 0.0 NOT NULL,
    total_cost FLOAT DEFAULT 0.0 NOT NULL,
    reference_type VARCHAR(50),
    reference_id VARCHAR(100),
    notes TEXT,
    created_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_stock_ledger_item ON stock_ledgers(inventory_item_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_stock_ledger_branch ON stock_ledgers(branch_id)")

# 16. stock_reservations (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS stock_reservations (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    quantity FLOAT DEFAULT 1.0 NOT NULL,
    reserved_for_type VARCHAR(50) NOT NULL,
    reserved_for_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'active' NOT NULL,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 17. suppliers (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS suppliers (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    supplier_type VARCHAR(30) DEFAULT 'legal_entity' NOT NULL,
    contact_name VARCHAR(100),
    phone VARCHAR(30) NOT NULL,
    email VARCHAR(100),
    gstin VARCHAR(25),
    pan VARCHAR(20),
    credit_period_days INTEGER DEFAULT 30 NOT NULL,
    credit_limit FLOAT DEFAULT 0.0 NOT NULL,
    payment_terms VARCHAR(100) DEFAULT 'Net 30' NOT NULL,
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    state_code VARCHAR(10),
    pincode VARCHAR(20),
    bank_details JSON DEFAULT '{}' NOT NULL,
    rating FLOAT DEFAULT 5.0 NOT NULL,
    tags JSON DEFAULT '[]' NOT NULL,
    notes TEXT,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_suppliers_name ON suppliers(name)")

# 18. purchase_orders & purchase_order_items (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS purchase_orders (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    supplier_id VARCHAR(36) NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    po_number VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(30) DEFAULT 'Draft' NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expected_delivery_date TIMESTAMP,
    subtotal FLOAT DEFAULT 0.0 NOT NULL,
    tax_total FLOAT DEFAULT 0.0 NOT NULL,
    grand_total FLOAT DEFAULT 0.0 NOT NULL,
    notes TEXT,
    created_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    approved_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_po_number ON purchase_orders(po_number)")

cur.execute("""
CREATE TABLE IF NOT EXISTS purchase_order_items (
    id VARCHAR(36) PRIMARY KEY,
    purchase_order_id VARCHAR(36) NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
    quantity_ordered FLOAT DEFAULT 1.0 NOT NULL,
    quantity_received FLOAT DEFAULT 0.0 NOT NULL,
    unit_cost FLOAT DEFAULT 0.0 NOT NULL,
    tax_rate FLOAT DEFAULT 18.0 NOT NULL,
    tax_amount FLOAT DEFAULT 0.0 NOT NULL,
    total_amount FLOAT DEFAULT 0.0 NOT NULL
)
""")

# 19. goods_received_notes & grn_items (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS goods_received_notes (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    purchase_order_id VARCHAR(36) REFERENCES purchase_orders(id) ON DELETE SET NULL,
    supplier_id VARCHAR(36) NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    grn_number VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(30) DEFAULT 'Completed' NOT NULL,
    received_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    vendor_invoice_no VARCHAR(100),
    vendor_invoice_date TIMESTAMP,
    vendor_invoice_amount FLOAT DEFAULT 0.0 NOT NULL,
    match_status VARCHAR(30) DEFAULT 'MATCHED' NOT NULL,
    match_notes TEXT,
    notes TEXT,
    received_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_grn_number ON goods_received_notes(grn_number)")

cur.execute("""
CREATE TABLE IF NOT EXISTS grn_items (
    id VARCHAR(36) PRIMARY KEY,
    grn_id VARCHAR(36) NOT NULL REFERENCES goods_received_notes(id) ON DELETE CASCADE,
    po_item_id VARCHAR(36) REFERENCES purchase_order_items(id) ON DELETE SET NULL,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
    warehouse_location_id VARCHAR(36) REFERENCES warehouse_locations(id) ON DELETE SET NULL,
    quantity_received FLOAT DEFAULT 0.0 NOT NULL,
    quantity_accepted FLOAT DEFAULT 0.0 NOT NULL,
    quantity_damaged FLOAT DEFAULT 0.0 NOT NULL,
    batch_number VARCHAR(100),
    expiry_date TIMESTAMP,
    unit_cost FLOAT DEFAULT 0.0 NOT NULL,
    notes TEXT
)
""")

# 20. branch_stock_transfers & items (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS branch_stock_transfers (
    id VARCHAR(36) PRIMARY KEY,
    transfer_number VARCHAR(50) UNIQUE NOT NULL,
    source_branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    destination_branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    status VARCHAR(30) DEFAULT 'requested' NOT NULL,
    requested_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    shipped_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    received_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    shipped_at TIMESTAMP,
    received_at TIMESTAMP,
    carrier_name VARCHAR(100),
    tracking_reference VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_transfer_number ON branch_stock_transfers(transfer_number)")

cur.execute("""
CREATE TABLE IF NOT EXISTS branch_stock_transfer_items (
    id VARCHAR(36) PRIMARY KEY,
    transfer_id VARCHAR(36) NOT NULL REFERENCES branch_stock_transfers(id) ON DELETE CASCADE,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
    quantity_requested FLOAT DEFAULT 1.0 NOT NULL,
    quantity_sent FLOAT DEFAULT 0.0 NOT NULL,
    quantity_received FLOAT DEFAULT 0.0 NOT NULL
)
""")

# 21. scrap_write_offs (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS scrap_write_offs (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
    warehouse_location_id VARCHAR(36) REFERENCES warehouse_locations(id) ON DELETE SET NULL,
    voucher_number VARCHAR(50) UNIQUE NOT NULL,
    quantity FLOAT NOT NULL,
    unit_cost FLOAT DEFAULT 0.0 NOT NULL,
    total_cost FLOAT DEFAULT 0.0 NOT NULL,
    reason_code VARCHAR(50) NOT NULL,
    notes TEXT,
    created_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    approved_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 22. stocktaking_audits & items (Phase 3)
cur.execute("""
CREATE TABLE IF NOT EXISTS stocktaking_audits (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    audit_number VARCHAR(50) UNIQUE NOT NULL,
    audit_type VARCHAR(30) DEFAULT 'blind_count' NOT NULL,
    status VARCHAR(30) DEFAULT 'in_progress' NOT NULL,
    notes TEXT,
    conducted_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    reviewed_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_stocktaking_number ON stocktaking_audits(audit_number)")

cur.execute("""
CREATE TABLE IF NOT EXISTS stocktaking_items (
    id VARCHAR(36) PRIMARY KEY,
    stocktaking_audit_id VARCHAR(36) NOT NULL REFERENCES stocktaking_audits(id) ON DELETE CASCADE,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
    warehouse_location_id VARCHAR(36) REFERENCES warehouse_locations(id) ON DELETE SET NULL,
    expected_quantity FLOAT DEFAULT 0.0 NOT NULL,
    counted_quantity FLOAT DEFAULT 0.0 NOT NULL,
    variance FLOAT DEFAULT 0.0 NOT NULL,
    unit_cost FLOAT DEFAULT 0.0 NOT NULL,
    variance_cost FLOAT DEFAULT 0.0 NOT NULL,
    manager_notes TEXT,
    adjustment_status VARCHAR(20) DEFAULT 'pending' NOT NULL
)
""")

# 23. tickets (Phase 4)
cur.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id VARCHAR(36) PRIMARY KEY,
    ticket_number VARCHAR(50) UNIQUE NOT NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    client_id VARCHAR(36) NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    asset_id VARCHAR(36) REFERENCES assets(id) ON DELETE SET NULL,
    ticket_type VARCHAR(30) DEFAULT 'service' NOT NULL,
    pipeline_id VARCHAR(36) REFERENCES status_pipelines(id) ON DELETE SET NULL,
    status VARCHAR(50) DEFAULT 'intake' NOT NULL,
    priority VARCHAR(20) DEFAULT 'standard' NOT NULL,
    assigned_tech_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    intake_source VARCHAR(50) DEFAULT 'counter' NOT NULL,
    intake_notes TEXT,
    problem_reported TEXT,
    diagnosis_notes TEXT,
    promised_delivery_date TIMESTAMP,
    customer_max_repair_budget FLOAT DEFAULT 0.0 NOT NULL,
    advance_deposit FLOAT DEFAULT 0.0 NOT NULL,
    total_parts_cost FLOAT DEFAULT 0.0 NOT NULL,
    total_labor_cost FLOAT DEFAULT 0.0 NOT NULL,
    tax_total FLOAT DEFAULT 0.0 NOT NULL,
    discount_amount FLOAT DEFAULT 0.0 NOT NULL,
    grand_total FLOAT DEFAULT 0.0 NOT NULL,
    paid_amount FLOAT DEFAULT 0.0 NOT NULL,
    balance_due FLOAT DEFAULT 0.0 NOT NULL,
    is_paused BOOLEAN DEFAULT 0 NOT NULL,
    pause_reason VARCHAR(255),
    tracking_token VARCHAR(64) UNIQUE NOT NULL,
    dynamic_fields JSON DEFAULT '{}' NOT NULL,
    qa_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    qa_checklist JSON DEFAULT '[]' NOT NULL,
    rma_details JSON DEFAULT '{}' NOT NULL,
    handover_at TIMESTAMP,
    handover_signature TEXT,
    handover_recipient VARCHAR(150),
    handover_notes TEXT,
    created_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tickets_number ON tickets(ticket_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tickets_branch ON tickets(branch_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tickets_client ON tickets(client_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tickets_tech ON tickets(assigned_tech_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tickets_token ON tickets(tracking_token)")

# 24. ticket_parts (Phase 4)
cur.execute("""
CREATE TABLE IF NOT EXISTS ticket_parts (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    inventory_item_id VARCHAR(36) NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    quantity FLOAT DEFAULT 1.0 NOT NULL,
    unit_cost FLOAT DEFAULT 0.0 NOT NULL,
    unit_price FLOAT DEFAULT 0.0 NOT NULL,
    tax_rate FLOAT DEFAULT 18.0 NOT NULL,
    total_price FLOAT DEFAULT 0.0 NOT NULL,
    is_reserved BOOLEAN DEFAULT 1 NOT NULL,
    reservation_id VARCHAR(36) REFERENCES stock_reservations(id) ON DELETE SET NULL,
    is_consumed BOOLEAN DEFAULT 0 NOT NULL,
    consumed_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ticket_parts_ticket ON ticket_parts(ticket_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ticket_parts_item ON ticket_parts(inventory_item_id)")

# 25. ticket_labor (Phase 4)
cur.execute("""
CREATE TABLE IF NOT EXISTS ticket_labor (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    service_catalog_item_id VARCHAR(36) REFERENCES service_catalog_items(id) ON DELETE SET NULL,
    name VARCHAR(200) NOT NULL,
    sac_code VARCHAR(20) DEFAULT '9987' NOT NULL,
    labor_price FLOAT DEFAULT 0.0 NOT NULL,
    tax_rate FLOAT DEFAULT 18.0 NOT NULL,
    total_price FLOAT DEFAULT 0.0 NOT NULL,
    commission_rate FLOAT DEFAULT 0.0 NOT NULL,
    commission_amount FLOAT DEFAULT 0.0 NOT NULL,
    assigned_tech_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    duration_minutes INTEGER DEFAULT 30 NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ticket_labor_ticket ON ticket_labor(ticket_id)")

# 26. ticket_media (Phase 4)
cur.execute("""
CREATE TABLE IF NOT EXISTS ticket_media (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    media_type VARCHAR(30) DEFAULT 'before' NOT NULL,
    file_url VARCHAR(500) NOT NULL,
    file_name VARCHAR(200),
    file_size_kb INTEGER DEFAULT 0 NOT NULL,
    notes TEXT,
    uploaded_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ticket_media_ticket ON ticket_media(ticket_id)")

# 27. ticket_estimates (Phase 4)
cur.execute("""
CREATE TABLE IF NOT EXISTS ticket_estimates (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    estimate_number VARCHAR(50) NOT NULL,
    approval_token VARCHAR(64) UNIQUE NOT NULL,
    approval_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    parts_subtotal FLOAT DEFAULT 0.0 NOT NULL,
    labor_subtotal FLOAT DEFAULT 0.0 NOT NULL,
    tax_total FLOAT DEFAULT 0.0 NOT NULL,
    grand_total FLOAT DEFAULT 0.0 NOT NULL,
    line_items JSON DEFAULT '[]' NOT NULL,
    customer_notes TEXT,
    approved_at TIMESTAMP,
    customer_ip VARCHAR(50),
    rejection_reason TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_estimates_ticket ON ticket_estimates(ticket_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_estimates_token ON ticket_estimates(approval_token)")

# 28. ticket_subcontracts (Phase 4)
cur.execute("""
CREATE TABLE IF NOT EXISTS ticket_subcontracts (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    vendor_name VARCHAR(150) NOT NULL,
    vendor_phone VARCHAR(30),
    task_description TEXT NOT NULL,
    cost FLOAT DEFAULT 0.0 NOT NULL,
    charged_to_customer FLOAT DEFAULT 0.0 NOT NULL,
    status VARCHAR(30) DEFAULT 'dispatched' NOT NULL,
    dispatch_date TIMESTAMP,
    expected_return_date TIMESTAMP,
    actual_return_date TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_subcontracts_ticket ON ticket_subcontracts(ticket_id)")

# 29. sales (Phase 5)
cur.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id VARCHAR(36) PRIMARY KEY,
    sale_number VARCHAR(50) UNIQUE NOT NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    client_id VARCHAR(36) REFERENCES clients(id) ON DELETE SET NULL,
    ticket_id VARCHAR(36) REFERENCES tickets(id) ON DELETE SET NULL,
    channel VARCHAR(30) DEFAULT 'counter_pos' NOT NULL,
    status VARCHAR(30) DEFAULT 'completed' NOT NULL,
    customer_name VARCHAR(150),
    customer_phone VARCHAR(30),
    customer_gstin VARCHAR(25),
    place_of_supply_state_code VARCHAR(10) DEFAULT '27' NOT NULL,
    tax_method VARCHAR(20) DEFAULT 'line_item' NOT NULL,
    subtotal FLOAT DEFAULT 0.0 NOT NULL,
    discount_type VARCHAR(20) DEFAULT 'fixed' NOT NULL,
    discount_amount FLOAT DEFAULT 0.0 NOT NULL,
    discount_approved_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    cgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    sgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    igst_amount FLOAT DEFAULT 0.0 NOT NULL,
    total_tax FLOAT DEFAULT 0.0 NOT NULL,
    round_off FLOAT DEFAULT 0.0 NOT NULL,
    grand_total FLOAT DEFAULT 0.0 NOT NULL,
    advance_offset_amount FLOAT DEFAULT 0.0 NOT NULL,
    paid_amount FLOAT DEFAULT 0.0 NOT NULL,
    balance_due FLOAT DEFAULT 0.0 NOT NULL,
    notes TEXT,
    created_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_sales_number ON sales(sale_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_sales_branch ON sales(branch_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_sales_channel ON sales(channel)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_sales_status ON sales(status)")

# 30. sale_lines (Phase 5)
cur.execute("""
CREATE TABLE IF NOT EXISTS sale_lines (
    id VARCHAR(36) PRIMARY KEY,
    sale_id VARCHAR(36) NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    item_type VARCHAR(20) DEFAULT 'inventory' NOT NULL,
    inventory_item_id VARCHAR(36) REFERENCES inventory_items(id) ON DELETE SET NULL,
    service_catalog_item_id VARCHAR(36) REFERENCES service_catalog_items(id) ON DELETE SET NULL,
    name VARCHAR(200) NOT NULL,
    sku_or_code VARCHAR(100),
    hsn_sac_code VARCHAR(20) DEFAULT '8504' NOT NULL,
    quantity FLOAT DEFAULT 1.0 NOT NULL,
    unit_price FLOAT DEFAULT 0.0 NOT NULL,
    discount_amount FLOAT DEFAULT 0.0 NOT NULL,
    taxable_amount FLOAT DEFAULT 0.0 NOT NULL,
    gst_rate FLOAT DEFAULT 18.0 NOT NULL,
    is_interstate BOOLEAN DEFAULT 0 NOT NULL,
    cgst_rate FLOAT DEFAULT 9.0 NOT NULL,
    cgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    sgst_rate FLOAT DEFAULT 9.0 NOT NULL,
    sgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    igst_rate FLOAT DEFAULT 0.0 NOT NULL,
    igst_amount FLOAT DEFAULT 0.0 NOT NULL,
    total_amount FLOAT DEFAULT 0.0 NOT NULL,
    warranty_days INTEGER DEFAULT 0 NOT NULL,
    serial_number VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_sale_lines_sale ON sale_lines(sale_id)")

# 31. invoices (Phase 5)
cur.execute("""
CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(36) PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    sale_id VARCHAR(36) NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    client_id VARCHAR(36) REFERENCES clients(id) ON DELETE SET NULL,
    invoice_type VARCHAR(30) DEFAULT 'b2c' NOT NULL,
    invoice_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    due_date TIMESTAMP NOT NULL,
    payment_terms_days INTEGER DEFAULT 30 NOT NULL,
    status VARCHAR(20) DEFAULT 'unpaid' NOT NULL,
    billing_name VARCHAR(200) NOT NULL,
    billing_address TEXT,
    billing_state VARCHAR(100) DEFAULT 'Maharashtra' NOT NULL,
    billing_state_code VARCHAR(10) DEFAULT '27' NOT NULL,
    billing_gstin VARCHAR(25),
    billing_pan VARCHAR(20),
    place_of_supply VARCHAR(10) DEFAULT '27' NOT NULL,
    is_reverse_charge BOOLEAN DEFAULT 0 NOT NULL,
    subtotal FLOAT DEFAULT 0.0 NOT NULL,
    total_tax FLOAT DEFAULT 0.0 NOT NULL,
    cgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    sgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    igst_amount FLOAT DEFAULT 0.0 NOT NULL,
    grand_total FLOAT DEFAULT 0.0 NOT NULL,
    advance_offset FLOAT DEFAULT 0.0 NOT NULL,
    amount_paid FLOAT DEFAULT 0.0 NOT NULL,
    balance_due FLOAT DEFAULT 0.0 NOT NULL,
    requires_eway_bill BOOLEAN DEFAULT 0 NOT NULL,
    eway_bill_number VARCHAR(50),
    eway_bill_date TIMESTAMP,
    irn_hash VARCHAR(100),
    irn_ack_no VARCHAR(50),
    irn_ack_date TIMESTAMP,
    irn_qr_code TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_invoices_number ON invoices(invoice_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_invoices_branch ON invoices(branch_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices(status)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_invoices_gstin ON invoices(billing_gstin)")

# 32. delivery_challans (Phase 5)
cur.execute("""
CREATE TABLE IF NOT EXISTS delivery_challans (
    id VARCHAR(36) PRIMARY KEY,
    challan_number VARCHAR(50) UNIQUE NOT NULL,
    sale_id VARCHAR(36) REFERENCES sales(id) ON DELETE SET NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    client_id VARCHAR(36) REFERENCES clients(id) ON DELETE SET NULL,
    challan_type VARCHAR(30) DEFAULT 'delivery' NOT NULL,
    dispatch_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    transporter_name VARCHAR(150),
    vehicle_number VARCHAR(50),
    eway_bill_number VARCHAR(50),
    status VARCHAR(20) DEFAULT 'dispatched' NOT NULL,
    items JSON DEFAULT '[]' NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_challans_number ON delivery_challans(challan_number)")

# 33. credit_notes (Phase 5)
cur.execute("""
CREATE TABLE IF NOT EXISTS credit_notes (
    id VARCHAR(36) PRIMARY KEY,
    credit_note_number VARCHAR(50) UNIQUE NOT NULL,
    invoice_id VARCHAR(36) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    client_id VARCHAR(36) REFERENCES clients(id) ON DELETE SET NULL,
    reason VARCHAR(100) DEFAULT 'Sales Return' NOT NULL,
    taxable_amount FLOAT DEFAULT 0.0 NOT NULL,
    cgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    sgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    igst_amount FLOAT DEFAULT 0.0 NOT NULL,
    total_credit_amount FLOAT DEFAULT 0.0 NOT NULL,
    status VARCHAR(20) DEFAULT 'active' NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_credit_notes_number ON credit_notes(credit_note_number)")

# 34. debit_notes (Phase 5)
cur.execute("""
CREATE TABLE IF NOT EXISTS debit_notes (
    id VARCHAR(36) PRIMARY KEY,
    debit_note_number VARCHAR(50) UNIQUE NOT NULL,
    invoice_id VARCHAR(36) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    client_id VARCHAR(36) REFERENCES clients(id) ON DELETE SET NULL,
    reason VARCHAR(100) DEFAULT 'Price Escalation' NOT NULL,
    taxable_amount FLOAT DEFAULT 0.0 NOT NULL,
    cgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    sgst_amount FLOAT DEFAULT 0.0 NOT NULL,
    igst_amount FLOAT DEFAULT 0.0 NOT NULL,
    total_debit_amount FLOAT DEFAULT 0.0 NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_debit_notes_number ON debit_notes(debit_note_number)")

# 35. payments (Phase 5)
cur.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id VARCHAR(36) PRIMARY KEY,
    payment_number VARCHAR(50) UNIQUE NOT NULL,
    sale_id VARCHAR(36) REFERENCES sales(id) ON DELETE SET NULL,
    invoice_id VARCHAR(36) REFERENCES invoices(id) ON DELETE SET NULL,
    client_id VARCHAR(36) REFERENCES clients(id) ON DELETE SET NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    method VARCHAR(30) DEFAULT 'cash' NOT NULL,
    amount FLOAT DEFAULT 0.0 NOT NULL,
    transaction_reference VARCHAR(100),
    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_reconciled BOOLEAN DEFAULT 0 NOT NULL,
    reconciled_at TIMESTAMP,
    reconciled_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    bank_statement_reference VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_payments_number ON payments(payment_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_payments_sale ON payments(sale_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_payments_invoice ON payments(invoice_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_payments_reconciled ON payments(is_reconciled)")

# 36. cash_register_shifts (Phase 6)
cur.execute("""
CREATE TABLE IF NOT EXISTS cash_register_shifts (
    id VARCHAR(36) PRIMARY KEY,
    shift_number VARCHAR(50) UNIQUE NOT NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    cashier_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    opening_float FLOAT DEFAULT 0.0 NOT NULL,
    opening_denominations JSON DEFAULT '{}' NOT NULL,
    closing_denominations JSON DEFAULT '{}' NOT NULL,
    closing_counted_cash FLOAT DEFAULT 0.0 NOT NULL,
    expected_cash FLOAT DEFAULT 0.0 NOT NULL,
    variance FLOAT DEFAULT 0.0 NOT NULL,
    is_balanced BOOLEAN DEFAULT 1 NOT NULL,
    variance_reason TEXT,
    manager_override_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT,
    audit_meta JSON DEFAULT '{}' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_shifts_number ON cash_register_shifts(shift_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_shifts_branch ON cash_register_shifts(branch_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_shifts_cashier ON cash_register_shifts(cashier_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_shifts_status ON cash_register_shifts(status)")

# 37. accounts (Phase 6)
cur.execute("""
CREATE TABLE IF NOT EXISTS accounts (
    id VARCHAR(36) PRIMARY KEY,
    account_number VARCHAR(50) UNIQUE NOT NULL,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL,
    currency VARCHAR(10) DEFAULT 'INR' NOT NULL,
    balance FLOAT DEFAULT 0.0 NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_accounts_number ON accounts(account_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_accounts_code ON accounts(code)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_accounts_type ON accounts(type)")

# 38. ledger_entries (Phase 6 Double-Entry Journal)
cur.execute("""
CREATE TABLE IF NOT EXISTS ledger_entries (
    id VARCHAR(36) PRIMARY KEY,
    transaction_group_id VARCHAR(36) NOT NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    shift_id VARCHAR(36) REFERENCES cash_register_shifts(id) ON DELETE SET NULL,
    account_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    reference_type VARCHAR(30) NOT NULL,
    reference_id VARCHAR(50),
    debit FLOAT DEFAULT 0.0 NOT NULL,
    credit FLOAT DEFAULT 0.0 NOT NULL,
    entry_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    narration TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ledger_group ON ledger_entries(transaction_group_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ledger_account ON ledger_entries(account_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_ledger_reference ON ledger_entries(reference_type, reference_id)")

# 39. expenses (Phase 6)
cur.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id VARCHAR(36) PRIMARY KEY,
    expense_number VARCHAR(50) UNIQUE NOT NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    shift_id VARCHAR(36) REFERENCES cash_register_shifts(id) ON DELETE SET NULL,
    category VARCHAR(100) DEFAULT 'General' NOT NULL,
    amount FLOAT DEFAULT 0.0 NOT NULL,
    payment_method VARCHAR(30) DEFAULT 'cash' NOT NULL,
    payee_name VARCHAR(150),
    receipt_photo_url VARCHAR(500),
    narration TEXT,
    ticket_id VARCHAR(36) REFERENCES tickets(id) ON DELETE SET NULL,
    is_spare_purchase BOOLEAN DEFAULT 0 NOT NULL,
    inventory_item_id VARCHAR(36) REFERENCES inventory_items(id) ON DELETE SET NULL,
    quantity FLOAT DEFAULT 0.0 NOT NULL,
    unit_cost FLOAT DEFAULT 0.0 NOT NULL,
    created_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_expenses_number ON expenses(expense_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_expenses_category ON expenses(category)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_expenses_ticket ON expenses(ticket_id)")

# 40. refunds (Phase 6)
cur.execute("""
CREATE TABLE IF NOT EXISTS refunds (
    id VARCHAR(36) PRIMARY KEY,
    refund_number VARCHAR(50) UNIQUE NOT NULL,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    shift_id VARCHAR(36) REFERENCES cash_register_shifts(id) ON DELETE SET NULL,
    sale_id VARCHAR(36) REFERENCES sales(id) ON DELETE SET NULL,
    invoice_id VARCHAR(36) REFERENCES invoices(id) ON DELETE SET NULL,
    credit_note_id VARCHAR(36) REFERENCES credit_notes(id) ON DELETE SET NULL,
    client_id VARCHAR(36) REFERENCES clients(id) ON DELETE SET NULL,
    original_payment_method VARCHAR(30) DEFAULT 'cash' NOT NULL,
    refund_payment_method VARCHAR(30) DEFAULT 'cash' NOT NULL,
    amount FLOAT DEFAULT 0.0 NOT NULL,
    reason VARCHAR(200) DEFAULT 'Customer Satisfaction' NOT NULL,
    status VARCHAR(20) DEFAULT 'completed' NOT NULL,
    approved_by_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_refunds_number ON refunds(refund_number)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_refunds_sale ON refunds(sale_id)")

# 41. commission_rules (Phase 6)
cur.execute("""
CREATE TABLE IF NOT EXISTS commission_rules (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) REFERENCES branches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) DEFAULT 'technician' NOT NULL,
    technician_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    rule_type VARCHAR(30) DEFAULT 'percentage_of_labor' NOT NULL,
    flat_amount FLOAT DEFAULT 0.0 NOT NULL,
    labor_percentage FLOAT DEFAULT 0.0 NOT NULL,
    tiers_config JSON DEFAULT '[]' NOT NULL,
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")

# 42. technician_commissions (Phase 6)
cur.execute("""
CREATE TABLE IF NOT EXISTS technician_commissions (
    id VARCHAR(36) PRIMARY KEY,
    branch_id VARCHAR(36) NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    technician_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    rule_id VARCHAR(36) REFERENCES commission_rules(id) ON DELETE SET NULL,
    labor_amount FLOAT DEFAULT 0.0 NOT NULL,
    rate_applied VARCHAR(50) DEFAULT '10%' NOT NULL,
    commission_amount FLOAT DEFAULT 0.0 NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tech_comm_tech ON technician_commissions(technician_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tech_comm_ticket ON technician_commissions(ticket_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_tech_comm_period ON technician_commissions(period_year, period_month)")

con.commit()
con.close()
print("✅ Database schema initialized for Phase 1 to Phase 6 successfully!")
