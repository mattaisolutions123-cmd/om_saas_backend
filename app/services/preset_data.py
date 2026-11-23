"""Industry Preset Definitions for OmniSuite Zero-Code Settings Engine

Presets:
1. Appliance/Motor Repair
2. Automotive Garage
3. Mobile/IT Repair
4. HVAC/Tailoring
"""

INDUSTRY_PRESETS = {
    "appliance_motor": {
        "key": "appliance_motor",
        "name": "Appliance / Motor Repair",
        "icon": "Wrench",
        "tagline": "Industrial & Consumer electrical motor rewinding, pump repair, and heavy appliances",
        "description": "Tailored for motor winding workshops, pump service centers, and home appliance repair centers with technical electrical specs, coil winding formulas, and multi-stage testing.",
        "custom_fields": [
            {
                "entity": "ticket",
                "field_key": "appliance_type",
                "name": "Appliance / Equipment Type",
                "field_type": "dropdown",
                "required": True,
                "options": [
                    {"label": "Submersible Pump", "value": "submersible_pump"},
                    {"label": "Three Phase Induction Motor", "value": "three_phase_motor"},
                    {"label": "Single Phase Motor", "value": "single_phase_motor"},
                    {"label": "Commercial Refrigerator", "value": "commercial_refrigerator"},
                    {"label": "Industrial Washing Machine", "value": "industrial_washing_machine"},
                    {"label": "Power Generator / Alternator", "value": "generator_alternator"}
                ],
                "sort_order": 1
            },
            {
                "entity": "ticket",
                "field_key": "power_rating_hp",
                "name": "Motor Rating (HP / kW)",
                "field_type": "number",
                "placeholder": "e.g. 7.5",
                "required": True,
                "sort_order": 2
            },
            {
                "entity": "ticket",
                "field_key": "voltage_phase",
                "name": "Voltage / Phase",
                "field_type": "dropdown",
                "options": [
                    {"label": "415V 3-Phase", "value": "415v_3p"},
                    {"label": "230V Single Phase", "value": "230v_1p"},
                    {"label": "110V AC", "value": "110v_ac"},
                    {"label": "24V / 48V DC", "value": "dc_motor"}
                ],
                "sort_order": 3
            },
            {
                "entity": "ticket",
                "field_key": "copper_wire_swg",
                "name": "Wire Gauge (SWG)",
                "field_type": "short_text",
                "placeholder": "e.g. 21 SWG Dual",
                "conditional_display": {"field": "appliance_type", "operator": "in", "value": ["three_phase_motor", "single_phase_motor", "submersible_pump"]},
                "sort_order": 4
            },
            {
                "entity": "ticket",
                "field_key": "copper_weight_kg",
                "name": "Copper Winding Weight (Kg)",
                "field_type": "number",
                "placeholder": "e.g. 4.25",
                "conditional_display": {"field": "appliance_type", "operator": "in", "value": ["three_phase_motor", "single_phase_motor", "submersible_pump"]},
                "sort_order": 5
            },
            {
                "entity": "ticket",
                "field_key": "copper_rate_per_kg",
                "name": "Copper Wire Rate/Kg (INR)",
                "field_type": "currency",
                "default_value": 920.0,
                "sort_order": 6
            },
            {
                "entity": "ticket",
                "field_key": "material_cost_calc",
                "name": "Total Wire Material Cost",
                "field_type": "formula",
                "formula_expression": {
                    "expression": "copper_weight_kg * copper_rate_per_kg",
                    "depends_on": ["copper_weight_kg", "copper_rate_per_kg"]
                },
                "sort_order": 7
            },
            {
                "entity": "ticket",
                "field_key": "intake_photo",
                "name": "Motor / Nameplate Photo",
                "field_type": "image_upload",
                "sort_order": 8
            },
            {
                "entity": "ticket",
                "field_key": "qr_barcode",
                "name": "Asset Barcode / Tag ID",
                "field_type": "barcode_scan",
                "sort_order": 9
            },
            {
                "entity": "ticket",
                "field_key": "customer_sign",
                "name": "Customer Intake Signature",
                "field_type": "signature_pad",
                "sort_order": 10
            },
            {
                "entity": "ticket",
                "field_key": "warranty_covered",
                "name": "Under Manufacturer Warranty",
                "field_type": "checkbox",
                "default_value": False,
                "sort_order": 11
            },
            {
                "entity": "ticket",
                "field_key": "technician_inspection_notes",
                "name": "Stator & Rotor Inspection Log",
                "field_type": "long_text",
                "role_visibility": ["owner", "branch_manager", "technician"],
                "sort_order": 12
            }
        ],
        "pipeline": {
            "name": "Motor & Heavy Appliance Pipeline",
            "code": "appliance_motor_pipeline",
            "entity": "ticket",
            "description": "End-to-end electrical diagnosis, rewinding, baking, QC insulation testing, and delivery",
            "statuses": [
                {"name": "Intake & Visual Check", "code": "intake", "bg_color": "#e0f2fe", "text_color": "#0369a1", "icon": "ClipboardList", "sort_order": 1, "is_initial": True},
                {"name": "Megger & Coil Diagnosis", "code": "diagnosis", "bg_color": "#fef3c7", "text_color": "#92400e", "icon": "Search", "sort_order": 2},
                {"name": "Estimate Approved", "code": "estimate_approved", "bg_color": "#dcfce7", "text_color": "#166534", "icon": "CheckCircle2", "sort_order": 3},
                {"name": "Rewinding & Bearing Change", "code": "in_repair", "bg_color": "#f3e8ff", "text_color": "#7e22ce", "icon": "Wrench", "sort_order": 4},
                {"name": "Varnish Baking & Drying", "code": "baking", "bg_color": "#ffedd5", "text_color": "#c2410c", "icon": "Flame", "sort_order": 5},
                {"name": "No-Load & Full-Load QC", "code": "testing_qc", "bg_color": "#ccfbf1", "text_color": "#0f766e", "icon": "ShieldCheck", "sort_order": 6},
                {"name": "Ready for Dispatch / Pickup", "code": "ready", "bg_color": "#bbf7d0", "text_color": "#15803d", "icon": "PackageCheck", "sort_order": 7},
                {"name": "Delivered to Customer", "code": "delivered", "bg_color": "#15803d", "text_color": "#ffffff", "icon": "Truck", "sort_order": 8, "is_terminal": True},
                {"name": "Unrepairable / Scrapped", "code": "scrapped", "bg_color": "#fee2e2", "text_color": "#991b1b", "icon": "XCircle", "sort_order": 9, "is_terminal": True}
            ],
            "transitions": [
                {"from_code": "intake", "to_code": "diagnosis", "name": "Begin Insulation Test", "guards": {}, "event_hooks": {"auto_create_task": {"enabled": True, "title": "Perform Megger insulation test", "assignee_role": "technician"}}},
                {"from_code": "diagnosis", "to_code": "estimate_approved", "name": "Customer Approved Estimate", "guards": {}, "event_hooks": {"send_sms": {"enabled": True, "template": "Dear {{client_name}}, your repair quote for Motor {{ticket_number}} is confirmed."}}},
                {"from_code": "estimate_approved", "to_code": "in_repair", "name": "Start Rewinding", "guards": {}, "event_hooks": {"lock_fields": ["power_rating_hp", "voltage_phase"]}},
                {"from_code": "in_repair", "to_code": "baking", "name": "Send to Baking Oven", "guards": {}, "event_hooks": {}},
                {"from_code": "baking", "to_code": "testing_qc", "name": "Proceed to QC Testing", "guards": {}, "event_hooks": {}},
                {"from_code": "testing_qc", "to_code": "ready", "name": "Pass QC Inspection", "guards": {}, "event_hooks": {"send_sms": {"enabled": True, "template": "Great news! Motor #{{ticket_number}} has passed testing and is ready for pickup."}}},
                {"from_code": "ready", "to_code": "delivered", "name": "Deliver Motor", "guards": {"closure_gate": True}, "event_hooks": {"send_sms": {"enabled": True, "template": "Motor #{{ticket_number}} delivered. Thank you for choosing our workshop!"}}},
                {"from_code": "diagnosis", "to_code": "scrapped", "name": "Core Burned Out Beyond Repair", "guards": {}, "event_hooks": {}}
            ]
        },
        "handbooks": [
            {
                "code": "brands_models",
                "name": "Motor & Equipment Brands",
                "is_hierarchical": True,
                "items": [
                    {"code": "kirloskar", "name": "Kirloskar Brothers", "children": [
                        {"code": "kirl_ch", "name": "CH Monobloc Series"},
                        {"code": "kirl_ks", "name": "KS4 Submersible"},
                        {"code": "kirl_ind", "name": "Induction IE3 Series"}
                    ]},
                    {"code": "crompton", "name": "Crompton Greaves", "children": [
                        {"code": "cg_mini", "name": "Mini Crest Water Pump"},
                        {"code": "cg_agri", "name": "Agri Master Openwell"},
                        {"code": "cg_flame", "name": "Flameproof IE2"}
                    ]},
                    {"code": "havells", "name": "Havells", "children": [
                        {"code": "hav_hi_flow", "name": "Hi-Flow Monobloc"},
                        {"code": "hav_ind", "name": "Energy Efficient TEFC"}
                    ]},
                    {"code": "abb", "name": "ABB Industrial", "children": [
                        {"code": "abb_m2ba", "name": "M2BAX Low Voltage Motor"},
                        {"code": "abb_m3bp", "name": "M3BP Process Performance"}
                    ]}
                ]
            },
            {
                "code": "defect_codes",
                "name": "Motor & Electrical Faults",
                "is_hierarchical": True,
                "items": [
                    {"code": "coil_defects", "name": "Coil & Insulation Defects", "children": [
                        {"code": "burn_phase", "name": "Single Phase Burnout", "extra_data": {"labels": {"hi": "सिंगल फेज बर्न", "en": "Single Phase Burnout"}}},
                        {"code": "insulation_break", "name": "Slot Ground Fault (Megger Zero)", "extra_data": {"labels": {"hi": "अर्थिंग फॉल्ट", "en": "Slot Ground Fault"}}},
                        {"code": "inter_turn_short", "name": "Inter-turn Short Circuit", "extra_data": {"labels": {"hi": "शॉर्ट सर्किट", "en": "Inter-turn Short Circuit"}}}
                    ]},
                    {"code": "mech_defects", "name": "Mechanical & Bearing Faults", "children": [
                        {"code": "bearing_seized", "name": "Bearing Jam / Seized (6205/6306)", "extra_data": {"labels": {"hi": "बेयरिंग जाम", "en": "Bearing Jam"}}},
                        {"code": "shaft_worn", "name": "Rotor Shaft Grooved / Runout", "extra_data": {"labels": {"hi": "शाफ्ट खराब", "en": "Rotor Shaft Grooved"}}},
                        {"code": "oil_seal_leak", "name": "Mechanical Seal Water Leak", "extra_data": {"labels": {"hi": "सील लीकेज", "en": "Mechanical Seal Water Leak"}}}
                    ]}
                ]
            },
            {
                "code": "units",
                "name": "Engineering Units",
                "is_hierarchical": False,
                "items": [
                    {"code": "hp", "name": "Horsepower (HP)"},
                    {"code": "kw", "name": "Kilowatt (kW)"},
                    {"code": "kg", "name": "Kilograms (Kg)"},
                    {"code": "meter", "name": "Meters (Mtr)"},
                    {"code": "swg", "name": "Standard Wire Gauge (SWG)"},
                    {"code": "pcs", "name": "Pieces (Pcs)"}
                ]
            },
            {
                "code": "payment_tags",
                "name": "Payment Modes",
                "is_hierarchical": False,
                "items": [
                    {"code": "cash", "name": "Workshop Cash Desk"},
                    {"code": "upi_qr", "name": "UPI / PhonePe / GPay QR"},
                    {"code": "bank_neft", "name": "Bank NEFT / RTGS (Corporate)"},
                    {"code": "cheque", "name": "Business Cheque"}
                ]
            },
            {
                "code": "expense_categories",
                "name": "Expense Classifications",
                "is_hierarchical": False,
                "items": [
                    {"code": "copper_wire", "name": "Copper Enamelled Wire Purchase"},
                    {"code": "insulation_varnish", "name": "Nomex Paper & Varnish Supplies"},
                    {"code": "bearings_hardware", "name": "SKF Bearings & Hardware"},
                    {"code": "workshop_electricity", "name": "Baking Oven Power Bills"}
                ]
            }
        ],
        "catalog_items": [
            {"name": "Complete 3-Phase Rewinding (up to 5HP)", "sku": "SRV-REWIND-5HP", "rate": 3500.0, "type": "service"},
            {"name": "Heavy Duty SKF 6306 2RS Bearing", "sku": "PRT-BRG-6306", "rate": 450.0, "type": "part"},
            {"name": "Varnish Dipping & Vacuum Drying", "sku": "SRV-VARNISH-01", "rate": 600.0, "type": "service"}
        ],
        "templates": [
            {
                "name": "Motor Intake Workshop Slip (80mm)",
                "type": "job_sheet",
                "paper_width": "80mm",
                "html_body": "<div style='font-family: monospace; font-size: 12px; width: 80mm; padding: 4px;'><div style='text-align: center; font-weight: bold;'>{{company_name}}<br/>MOTOR REPAIR WORKSHOP</div><hr/><div>Job#: <b>{{ticket_number}}</b> Date: {{created_at}}</div><div>Client: {{customer_name}} ({{customer_phone}})</div><div>Equipment: <b>{{appliance_type}}</b></div><div>Rating: {{power_rating_hp}} HP | {{voltage_phase}}</div><hr/><div>Fault: {{defect_name}}</div><div>Est. Wire: {{copper_weight_kg}} Kg SWG {{copper_wire_swg}}</div><hr/><div style='font-size: 10px; text-align: center;'>Please retain slip for motor collection.<br/>Balance due on delivery.</div></div>",
                "variables": ["company_name", "ticket_number", "created_at", "customer_name", "customer_phone", "appliance_type", "power_rating_hp", "voltage_phase", "defect_name", "copper_weight_kg", "copper_wire_swg"]
            },
            {
                "name": "Tax Invoice - Motor Service (A4)",
                "type": "invoice",
                "paper_width": "A4",
                "html_body": "<div style='font-family: Arial, sans-serif; padding: 24px; max-width: 800px; margin: 0 auto;'><div style='display: flex; justify-content: space-between;'><div><h2 style='margin:0;'>{{company_name}}</h2><p>{{branch_address}}<br/>GSTIN: {{branch_gstin}} | State: {{state_code}}</p></div><div style='text-align: right;'><h1 style='color: #0284c7; margin:0;'>TAX INVOICE</h1><p>Invoice #: {{invoice_number}}<br/>Date: {{invoice_date}}</p></div></div><hr style='border: 1px solid #e2e8f0; margin: 16px 0;'/><div><b>Billed To:</b> {{customer_name}} ({{customer_phone}})<br/>Equipment: {{appliance_type}} - {{power_rating_hp}} HP</div><table style='width: 100%; border-collapse: collapse; margin-top: 16px;'><thead style='background: #f8fafc;'><tr><th style='border: 1px solid #cbd5e1; padding: 8px; text-align: left;'>Item & Description</th><th style='border: 1px solid #cbd5e1; padding: 8px; text-align: right;'>Qty</th><th style='border: 1px solid #cbd5e1; padding: 8px; text-align: right;'>Rate</th><th style='border: 1px solid #cbd5e1; padding: 8px; text-align: right;'>Amount (INR)</th></tr></thead><tbody>{{items_rows}}</tbody></table><div style='margin-top: 16px; text-align: right;'><p>Subtotal: ₹{{subtotal}}<br/>CGST + SGST (18%): ₹{{tax_amount}}<br/><b>Grand Total: ₹{{total_amount}}</b><br/>Amount Paid: ₹{{paid_amount}}<br/><b style='color: #b91c1c;'>Balance Due: ₹{{balance_due}}</b></p></div></div>",
                "variables": ["company_name", "branch_address", "branch_gstin", "state_code", "invoice_number", "invoice_date", "customer_name", "customer_phone", "appliance_type", "power_rating_hp", "items_rows", "subtotal", "tax_amount", "total_amount", "paid_amount", "balance_due"]
            }
        ]
    },

    "automotive_garage": {
        "key": "automotive_garage",
        "name": "Automotive Garage",
        "icon": "Car",
        "tagline": "Multi-brand car & bike service station, detailing, body shop & mechanicals",
        "description": "Equipped with vehicle registration number, odometer tracking, fuel gauge, insurance claim tracking, Bay assignments, and multi-point vehicle health checklist.",
        "custom_fields": [
            {
                "entity": "ticket",
                "field_key": "vehicle_reg_no",
                "name": "Vehicle Registration Number",
                "field_type": "short_text",
                "placeholder": "e.g. MH 02 CD 1234",
                "required": True,
                "unique": True,
                "sort_order": 1
            },
            {
                "entity": "ticket",
                "field_key": "odometer_reading_km",
                "name": "Odometer (KM)",
                "field_type": "number",
                "placeholder": "e.g. 45200",
                "required": True,
                "sort_order": 2
            },
            {
                "entity": "ticket",
                "field_key": "fuel_level",
                "name": "Fuel Tank Level",
                "field_type": "dropdown",
                "options": [
                    {"label": "Reserve / Empty (<10%)", "value": "reserve"},
                    {"label": "1/4 Tank (25%)", "value": "quarter"},
                    {"label": "1/2 Tank (50%)", "value": "half"},
                    {"label": "3/4 Tank (75%)", "value": "three_quarters"},
                    {"label": "Full Tank (100%)", "value": "full"}
                ],
                "required": True,
                "sort_order": 3
            },
            {
                "entity": "ticket",
                "field_key": "fuel_type",
                "name": "Engine Fuel Type",
                "field_type": "dropdown",
                "options": [
                    {"label": "Petrol", "value": "petrol"},
                    {"label": "Diesel", "value": "diesel"},
                    {"label": "CNG / Bi-Fuel", "value": "cng"},
                    {"label": "Electric (EV)", "value": "ev"},
                    {"label": "Hybrid", "value": "hybrid"}
                ],
                "sort_order": 4
            },
            {
                "entity": "ticket",
                "field_key": "chassis_vin",
                "name": "Chassis / VIN Number",
                "field_type": "short_text",
                "placeholder": "17-digit VIN",
                "sort_order": 5
            },
            {
                "entity": "ticket",
                "field_key": "insurance_policy_no",
                "name": "Insurance Company & Policy No",
                "field_type": "short_text",
                "placeholder": "e.g. ICICI Lombard - #928374",
                "sort_order": 6
            },
            {
                "entity": "ticket",
                "field_key": "car_dent_scratch_photo",
                "name": "Vehicle 360° Inspection Photos",
                "field_type": "image_upload",
                "sort_order": 7
            },
            {
                "entity": "ticket",
                "field_key": "valuable_belongings_left",
                "name": "Personal Belongings Removed by Owner",
                "field_type": "checkbox",
                "default_value": True,
                "sort_order": 8
            },
            {
                "entity": "ticket",
                "field_key": "customer_intake_sign",
                "name": "Job Card Authorization Signature",
                "field_type": "signature_pad",
                "required": True,
                "sort_order": 9
            },
            {
                "entity": "ticket",
                "field_key": "service_advisor_notes",
                "name": "Customer Complaint Description",
                "field_type": "long_text",
                "placeholder": "e.g. Squeaking brake noise on deceleration, AC cooling low",
                "sort_order": 10
            }
        ],
        "pipeline": {
            "name": "Auto Garage Service Pipeline",
            "code": "auto_garage_pipeline",
            "entity": "ticket",
            "description": "Standard 7-step vehicle servicing workflow from bay check-in to final road test & wash",
            "statuses": [
                {"name": "Vehicle Check-in & Intake", "code": "intake", "bg_color": "#e0f2fe", "text_color": "#0369a1", "icon": "Car", "sort_order": 1, "is_initial": True},
                {"name": "Bay Inspection & Job Card", "code": "inspection", "bg_color": "#fef3c7", "text_color": "#92400e", "icon": "ClipboardCheck", "sort_order": 2},
                {"name": "Parts Requisitioned", "code": "parts_ordered", "bg_color": "#f3e8ff", "text_color": "#7e22ce", "icon": "Package", "sort_order": 3},
                {"name": "Service / Repair in Progress", "code": "in_progress", "bg_color": "#fed7aa", "text_color": "#9a3412", "icon": "Wrench", "sort_order": 4},
                {"name": "Road Test & Quality Audit", "code": "road_test", "bg_color": "#ccfbf1", "text_color": "#0f766e", "icon": "Gauge", "sort_order": 5},
                {"name": "Washing & Detailing", "code": "wash_detailing", "bg_color": "#e0e7ff", "text_color": "#3730a3", "icon": "Sparkles", "sort_order": 6},
                {"name": "Ready for Gate Pass", "code": "ready", "bg_color": "#bbf7d0", "text_color": "#15803d", "icon": "KeyRound", "sort_order": 7},
                {"name": "Vehicle Delivered", "code": "delivered", "bg_color": "#15803d", "text_color": "#ffffff", "icon": "CheckCheck", "sort_order": 8, "is_terminal": True}
            ],
            "transitions": [
                {"from_code": "intake", "to_code": "inspection", "name": "Assign to Ramp / Bay", "guards": {}, "event_hooks": {"auto_create_task": {"enabled": True, "title": "Perform 40-point vehicle inspection", "assignee_role": "technician"}}},
                {"from_code": "inspection", "to_code": "parts_ordered", "name": "Requisition Spare Parts", "guards": {}, "event_hooks": {}},
                {"from_code": "parts_ordered", "to_code": "in_progress", "name": "Parts Issued to Bay", "guards": {}, "event_hooks": {}},
                {"from_code": "in_progress", "to_code": "road_test", "name": "Mechanical Work Done", "guards": {}, "event_hooks": {}},
                {"from_code": "road_test", "to_code": "wash_detailing", "name": "Road Test Passed", "guards": {}, "event_hooks": {}},
                {"from_code": "wash_detailing", "to_code": "ready", "name": "Washing Complete", "guards": {}, "event_hooks": {"send_sms": {"enabled": True, "template": "Hello {{client_name}}, your vehicle {{vehicle_reg_no}} is serviced, washed, and ready for pickup!"}}},
                {"from_code": "ready", "to_code": "delivered", "name": "Issue Gate Pass & Handover", "guards": {"closure_gate": True}, "event_hooks": {"send_sms": {"enabled": True, "template": "Vehicle {{vehicle_reg_no}} delivered. Safe travels from {{company_name}}!"}}}
            ]
        },
        "handbooks": [
            {
                "code": "brands_models",
                "name": "Vehicle Makes & Models",
                "is_hierarchical": True,
                "items": [
                    {"code": "maruti", "name": "Maruti Suzuki", "children": [
                        {"code": "ms_swift", "name": "Swift"},
                        {"code": "ms_baleno", "name": "Baleno"},
                        {"code": "ms_brezza", "name": "Brezza"},
                        {"code": "ms_ertiga", "name": "Ertiga"}
                    ]},
                    {"code": "hyundai", "name": "Hyundai", "children": [
                        {"code": "hy_i20", "name": "i20"},
                        {"code": "hy_creta", "name": "Creta"},
                        {"code": "hy_venue", "name": "Venue"}
                    ]},
                    {"code": "tata", "name": "Tata Motors", "children": [
                        {"code": "tata_nexon", "name": "Nexon / EV"},
                        {"code": "tata_punch", "name": "Punch"},
                        {"code": "tata_harrier", "name": "Harrier"}
                    ]},
                    {"code": "toyota", "name": "Toyota", "children": [
                        {"code": "toy_innova", "name": "Innova Crysta / Hycross"},
                        {"code": "toy_fortuner", "name": "Fortuner"},
                        {"code": "toy_glanza", "name": "Glanza"}
                    ]}
                ]
            },
            {
                "code": "defect_codes",
                "name": "Automotive Faults & Services",
                "is_hierarchical": True,
                "items": [
                    {"code": "periodic_maintenance", "name": "Periodic Scheduled Maintenance", "children": [
                        {"code": "pms_10k", "name": "10,000 KM Engine Oil & Filter Service", "extra_data": {"labels": {"hi": "10k किमी आयल सर्विस", "en": "10k Oil Service"}}},
                        {"code": "brake_pad_disc", "name": "Front Brake Pad Replacement & Disc Skimming", "extra_data": {"labels": {"hi": "ब्रेक पैड बदलना", "en": "Brake Pad Change"}}},
                        {"code": "wheel_alignment", "name": "3D Wheel Alignment & Balancing", "extra_data": {"labels": {"hi": "व्हील अलाइनमेंट", "en": "Wheel Alignment"}}}
                    ]},
                    {"code": "engine_transmission", "name": "Engine, Cooling & Clutch", "children": [
                        {"code": "clutch_plate_overhaul", "name": "Clutch Plate & Release Bearing Overhaul", "extra_data": {"labels": {"hi": "क्लच प्लेट काम", "en": "Clutch Overhaul"}}},
                        {"code": "ac_condenser_leak", "name": "AC Gas Leak & Condenser Flush", "extra_data": {"labels": {"hi": "एसी गैस लीकेज", "en": "AC Gas Leak"}}},
                        {"code": "suspension_lower_arm", "name": "Suspension Bushing & Strut Replacement", "extra_data": {"labels": {"hi": "सस्पेंशन काम", "en": "Suspension Overhaul"}}}
                    ]}
                ]
            },
            {
                "code": "units",
                "name": "Garage Units",
                "is_hierarchical": False,
                "items": [
                    {"code": "ltr", "name": "Liters (Ltr)"},
                    {"code": "sets", "name": "Sets (Front/Rear)"},
                    {"code": "km", "name": "Kilometers (KM)"},
                    {"code": "pcs", "name": "Pieces (Pcs)"},
                    {"code": "hours", "name": "Labor Hours (Hr)"}
                ]
            },
            {
                "code": "payment_tags",
                "name": "Payment Modes",
                "is_hierarchical": False,
                "items": [
                    {"code": "cash", "name": "Cash Desk"},
                    {"code": "upi_qr", "name": "UPI Static / Dynamic QR"},
                    {"code": "pos_card", "name": "Credit / Debit Card EDC"},
                    {"code": "insurance_cashless", "name": "Insurance Cashless Claim"}
                ]
            },
            {
                "code": "expense_categories",
                "name": "Garage Operational Expenses",
                "is_hierarchical": False,
                "items": [
                    {"code": "oils_lubricants", "name": "Synthetic Engine Oils & Coolant"},
                    {"code": "oem_spare_parts", "name": "OEM Spare Parts Inventory"},
                    {"code": "wash_chemical", "name": "Car Shampoo & Wax Polishes"},
                    {"code": "scrap_disposal", "name": "Used Engine Oil Disposal"}
                ]
            }
        ],
        "catalog_items": [
            {"name": "Fully Synthetic 5W-30 Engine Oil (3.5L)", "sku": "OIL-SYN-5W30", "rate": 2200.0, "type": "part"},
            {"name": "Comprehensive General Service (Petrol)", "sku": "SRV-GEN-PETROL", "rate": 1850.0, "type": "service"},
            {"name": "Foam Wash & Interior Vacuuming", "sku": "SRV-WASH-INT", "rate": 650.0, "type": "service"}
        ],
        "templates": [
            {
                "name": "Garage Job Card & Gate Pass (A4)",
                "type": "job_sheet",
                "paper_width": "A4",
                "html_body": "<div style='font-family: Arial, sans-serif; padding: 20px; border: 2px solid #0284c7;'><div style='display: flex; justify-content: space-between;'><div><h2>{{company_name}} - JOB CARD & GATE PASS</h2><p>Branch: {{branch_name}} | Phone: {{branch_phone}}</p></div><div style='text-align: right;'><h3 style='margin:0;'>JC#: {{ticket_number}}</h3><p>Date: {{created_at}}</p></div></div><hr/><div style='display: flex; justify-content: space-between; background: #f1f5f9; padding: 10px;'><div><b>Reg No:</b> {{vehicle_reg_no}}<br/><b>Make/Model:</b> {{brand_model}}<br/><b>Fuel:</b> {{fuel_type}} ({{fuel_level}})</div><div><b>Odometer:</b> {{odometer_reading_km}} KM<br/><b>Customer:</b> {{customer_name}}<br/><b>Phone:</b> {{customer_phone}}</div></div><div style='margin-top: 16px;'><b>Reported Issues:</b><p>{{service_advisor_notes}}</p></div><div style='margin-top: 30px; display: flex; justify-content: space-between;'><div>____________________<br/>Customer Signature</div><div>____________________<br/>Service Advisor Signature</div></div></div>",
                "variables": ["company_name", "branch_name", "branch_phone", "ticket_number", "created_at", "vehicle_reg_no", "brand_model", "fuel_type", "fuel_level", "odometer_reading_km", "customer_name", "customer_phone", "service_advisor_notes"]
            },
            {
                "name": "Vehicle Gate Clearance Receipt (80mm)",
                "type": "receipt",
                "paper_width": "80mm",
                "html_body": "<div style='font-family: monospace; font-size: 12px; width: 80mm; padding: 4px;'><div style='text-align: center; font-weight: bold;'>{{company_name}}<br/>VEHICLE GATE PASS</div><hr/><div>JC#: {{ticket_number}}</div><div>Reg: <b>{{vehicle_reg_no}}</b></div><div>Odo: {{odometer_reading_km}} KM</div><div>Client: {{customer_name}}</div><hr/><div>Invoice Total: ₹{{total_amount}}</div><div>Paid in Full: ₹{{paid_amount}}</div><div style='font-weight: bold;'>Balance Due: ₹{{balance_due}}</div><hr/><div style='text-align: center; font-size: 10px;'>GATE PASS APPROVED FOR EXIT<br/>Security Check Stamp Required</div></div>",
                "variables": ["company_name", "ticket_number", "vehicle_reg_no", "odometer_reading_km", "customer_name", "total_amount", "paid_amount", "balance_due"]
            }
        ]
    },

    "mobile_it_repair": {
        "key": "mobile_it_repair",
        "name": "Mobile / IT Repair",
        "icon": "Smartphone",
        "tagline": "Smartphones, laptops, MacBooks, tablets, logic board & micro-soldering",
        "description": "Pre-configured for IMEI barcode scanning, unlock pattern/PIN recording, screen condition inspection, liquid damage verification, and fast thermal sticker tagging.",
        "custom_fields": [
            {
                "entity": "ticket",
                "field_key": "device_category",
                "name": "Device Category",
                "field_type": "dropdown",
                "required": True,
                "options": [
                    {"label": "Smartphone (Android)", "value": "android_phone"},
                    {"label": "iPhone (Apple iOS)", "value": "iphone"},
                    {"label": "Laptop / MacBook", "value": "laptop"},
                    {"label": "Tablet / iPad", "value": "tablet"},
                    {"label": "Desktop / iMac", "value": "desktop"},
                    {"label": "Smartwatch / Wearable", "value": "wearable"}
                ],
                "sort_order": 1
            },
            {
                "entity": "ticket",
                "field_key": "imei_serial_no",
                "name": "IMEI / Serial Number",
                "field_type": "barcode_scan",
                "placeholder": "Scan or enter 15-digit IMEI",
                "required": True,
                "sort_order": 2
            },
            {
                "entity": "ticket",
                "field_key": "device_passcode",
                "name": "Unlock Screen PIN / Pattern Note",
                "field_type": "short_text",
                "placeholder": "e.g. 1234 or L-shape",
                "sort_order": 3
            },
            {
                "entity": "ticket",
                "field_key": "liquid_damage_indicator",
                "name": "Liquid Damage Indicator (Red Dot)",
                "field_type": "checkbox",
                "default_value": False,
                "sort_order": 4
            },
            {
                "entity": "ticket",
                "field_key": "cosmetic_condition",
                "name": "Pre-existing Scratches / Dents",
                "field_type": "multi_select",
                "options": [
                    {"label": "Back Glass Cracked", "value": "back_cracked"},
                    {"label": "Side Bezel Scratched", "value": "bezel_scratched"},
                    {"label": "Screen Already Broken", "value": "screen_broken"},
                    {"label": "Missing Screws / Parts", "value": "missing_screws"},
                    {"label": "Camera Lens Scratched", "value": "camera_scratched"}
                ],
                "sort_order": 5
            },
            {
                "entity": "ticket",
                "field_key": "intake_device_photos",
                "name": "Intake Cosmetic Photographs",
                "field_type": "image_upload",
                "sort_order": 6
            },
            {
                "entity": "ticket",
                "field_key": "data_loss_consent",
                "name": "Customer Consents: Not responsible for unbacked data",
                "field_type": "checkbox",
                "required": True,
                "default_value": True,
                "sort_order": 7
            },
            {
                "entity": "ticket",
                "field_key": "customer_signature",
                "name": "Customer Intake Signature",
                "field_type": "signature_pad",
                "required": True,
                "sort_order": 8
            },
            {
                "entity": "ticket",
                "field_key": "technician_bench_findings",
                "name": "Microscope & Thermal Cam Diagnostics",
                "field_type": "long_text",
                "role_visibility": ["owner", "branch_manager", "technician"],
                "sort_order": 9
            }
        ],
        "pipeline": {
            "name": "Mobile & IT Service Pipeline",
            "code": "mobile_it_pipeline",
            "entity": "ticket",
            "description": "Quick-turnaround electronic repair with customer quotation gate and automated SMS",
            "statuses": [
                {"name": "Intake & Barcode Tagged", "code": "intake", "bg_color": "#e0f2fe", "text_color": "#0369a1", "icon": "Barcode", "sort_order": 1, "is_initial": True},
                {"name": "Bench Diagnosis & Quote", "code": "diagnosis", "bg_color": "#fef3c7", "text_color": "#92400e", "icon": "Microscope", "sort_order": 2},
                {"name": "Customer Quoted / Pending Approval", "code": "quoted", "bg_color": "#f3e8ff", "text_color": "#7e22ce", "icon": "PhoneCall", "sort_order": 3},
                {"name": "Repair in Progress", "code": "in_repair", "bg_color": "#fed7aa", "text_color": "#9a3412", "icon": "Cpu", "sort_order": 4},
                {"name": "Waiting for Spare Part", "code": "waiting_parts", "bg_color": "#f1f5f9", "text_color": "#475569", "icon": "Clock", "sort_order": 5},
                {"name": "Bench QC & Sensor Testing", "code": "qc_passed", "bg_color": "#ccfbf1", "text_color": "#0f766e", "icon": "CheckSquare", "sort_order": 6},
                {"name": "Ready for Pickup", "code": "ready", "bg_color": "#bbf7d0", "text_color": "#15803d", "icon": "BellRing", "sort_order": 7},
                {"name": "Device Delivered", "code": "delivered", "bg_color": "#15803d", "text_color": "#ffffff", "icon": "PackageCheck", "sort_order": 8, "is_terminal": True},
                {"name": "Returned Unrepaired (RUR)", "code": "rur", "bg_color": "#fee2e2", "text_color": "#991b1b", "icon": "Undo2", "sort_order": 9, "is_terminal": True}
            ],
            "transitions": [
                {"from_code": "intake", "to_code": "diagnosis", "name": "Handover to Tech Bench", "guards": {}, "event_hooks": {}},
                {"from_code": "diagnosis", "to_code": "quoted", "name": "Send Estimate to Customer", "guards": {}, "event_hooks": {"send_sms": {"enabled": True, "template": "Hi {{client_name}}, repair estimate for {{brand_model}} is ₹{{total_amount}}. Reply YES to proceed."}}},
                {"from_code": "quoted", "to_code": "in_repair", "name": "Customer Approved Quote", "guards": {}, "event_hooks": {"lock_fields": ["device_category", "imei_serial_no"]}},
                {"from_code": "in_repair", "to_code": "waiting_parts", "name": "Part Out of Stock", "guards": {}, "event_hooks": {"auto_create_task": {"enabled": True, "title": "Source replacement display / IC", "assignee_role": "branch_manager"}}},
                {"from_code": "waiting_parts", "to_code": "in_repair", "name": "Part Received", "guards": {}, "event_hooks": {}},
                {"from_code": "in_repair", "to_code": "qc_passed", "name": "Repair Finished - Run QC", "guards": {}, "event_hooks": {}},
                {"from_code": "qc_passed", "to_code": "ready", "name": "QC Approved", "guards": {}, "event_hooks": {"send_sms": {"enabled": True, "template": "Your device {{brand_model}} (Job #{{ticket_number}}) is ready! Balance: ₹{{balance_due}}."}}},
                {"from_code": "ready", "to_code": "delivered", "name": "Handover Device", "guards": {"closure_gate": True}, "event_hooks": {"send_sms": {"enabled": True, "template": "Thank you for trusting {{company_name}}! 30-day warranty active."}}},
                {"from_code": "quoted", "to_code": "rur", "name": "Customer Rejected Estimate", "guards": {}, "event_hooks": {}}
            ]
        },
        "handbooks": [
            {
                "code": "brands_models",
                "name": "Electronics Brands & Models",
                "is_hierarchical": True,
                "items": [
                    {"code": "apple", "name": "Apple", "children": [
                        {"code": "ip_13", "name": "iPhone 13"},
                        {"code": "ip_14pro", "name": "iPhone 14 Pro"},
                        {"code": "ip_15", "name": "iPhone 15"},
                        {"code": "mbp_m2", "name": "MacBook Pro 14 (M2)"}
                    ]},
                    {"code": "samsung", "name": "Samsung", "children": [
                        {"code": "sam_s23", "name": "Galaxy S23 Ultra"},
                        {"code": "sam_a54", "name": "Galaxy A54 5G"},
                        {"code": "sam_zflip", "name": "Galaxy Z Flip 5"}
                    ]},
                    {"code": "dell_hp", "name": "Laptops (Dell / HP)", "children": [
                        {"code": "dell_xps13", "name": "Dell XPS 13"},
                        {"code": "hp_pavilion", "name": "HP Pavilion 15 Gaming"},
                        {"code": "lenovo_t14", "name": "Lenovo ThinkPad T14"}
                    ]}
                ]
            },
            {
                "code": "defect_codes",
                "name": "Mobile / Laptop Fault Codes",
                "is_hierarchical": True,
                "items": [
                    {"code": "display_touch", "name": "Display & Touch Screen", "children": [
                        {"code": "oled_lines", "name": "Green/White OLED Lines", "extra_data": {"labels": {"hi": "स्क्रीन पर लाइनें", "en": "OLED Lines"}}},
                        {"code": "touch_not_working", "name": "Digitizer Touch Ghosting/Dead", "extra_data": {"labels": {"hi": "टच काम नहीं कर रहा", "en": "Touch Dead"}}},
                        {"code": "glass_cracked_only", "name": "Front Glass Only (OCA Laminate)", "extra_data": {"labels": {"hi": "सिर्फ शीशा टूटा", "en": "Glass Only"}}}
                    ]},
                    {"code": "power_charging", "name": "Power, Charging & Battery", "children": [
                        {"code": "battery_swollen", "name": "Battery 0% or Swollen (80% Health)", "extra_data": {"labels": {"hi": "बैटरी फुली हुई", "en": "Battery Swollen"}}},
                        {"code": "type_c_port_burnt", "name": "USB-C Port Moisture / CC Pin Short", "extra_data": {"labels": {"hi": "चार्जिंग पिन ख़राब", "en": "Charging Port Defect"}}},
                        {"code": "pmic_dead", "name": "Motherboard Power IC Short (0.00A Draw)", "extra_data": {"labels": {"hi": "मदरबोर्ड डेड", "en": "PMIC Short"}}}
                    ]}
                ]
            },
            {
                "code": "units",
                "name": "IT Hardware Units",
                "is_hierarchical": False,
                "items": [
                    {"code": "pcs", "name": "Pieces (Pcs)"},
                    {"code": "units", "name": "Units (Unit)"},
                    {"code": "gb", "name": "Gigabytes (GB)"},
                    {"code": "mb", "name": "Megabytes (MB)"}
                ]
            },
            {
                "code": "payment_tags",
                "name": "POS Payment Modes",
                "is_hierarchical": False,
                "items": [
                    {"code": "cash", "name": "Counter Cash"},
                    {"code": "upi", "name": "Instant UPI QR (Paytm/GPay)"},
                    {"code": "card", "name": "Credit/Debit Card POS"}
                ]
            },
            {
                "code": "expense_categories",
                "name": "Shop Spares & Consumables",
                "is_hierarchical": False,
                "items": [
                    {"code": "screen_assemblies", "name": "OEM & First Copy Screen Assemblies"},
                    {"code": "batteries_charging", "name": "Replacement Batteries & Flex Cables"},
                    {"code": "bga_soldering", "name": "Solder Paste, Flux, Wick & Thermal Pads"}
                ]
            }
        ],
        "catalog_items": [
            {"name": "Original OLED Display Replacement", "sku": "DSP-OLED-GEN", "rate": 4500.0, "type": "part"},
            {"name": "High Capacity Replacement Battery", "sku": "BAT-LI-ION", "rate": 1800.0, "type": "part"},
            {"name": "Motherboard Ultrasonic Cleaner & Micro-solder", "sku": "SRV-SOLDER-L1", "rate": 1200.0, "type": "service"}
        ],
        "templates": [
            {
                "name": "58mm Barcode Sticker Tag",
                "type": "barcode_label",
                "paper_width": "58mm",
                "html_body": "<div style='font-family: monospace; font-size: 11px; width: 58mm; padding: 2px; text-align: center;'><div style='font-weight: bold;'>{{company_name}}</div><div>Job: <b>#{{ticket_number}}</b></div><div style='font-size: 14px; font-weight: bold; margin: 4px 0;'>*{{ticket_number}}*</div><div>{{brand_model}}</div><div>IMEI: {{imei_serial_no}}</div><div>PIN: {{device_passcode}}</div><div>Client: {{customer_name}}</div></div>",
                "variables": ["company_name", "ticket_number", "brand_model", "imei_serial_no", "device_passcode", "customer_name"]
            },
            {
                "name": "Thermal Customer Claim Slip (80mm)",
                "type": "receipt",
                "paper_width": "80mm",
                "html_body": "<div style='font-family: monospace; font-size: 12px; width: 80mm; padding: 4px;'><div style='text-align: center; font-weight: bold;'>{{company_name}}<br/>MOBILE & IT SERVICE CENTER</div><hr/><div>Job#: <b>{{ticket_number}}</b> | {{created_at}}</div><div>Device: <b>{{brand_model}}</b></div><div>IMEI: {{imei_serial_no}}</div><div>Issue: {{defect_name}}</div><hr/><div>Est. Cost: ₹{{total_amount}}</div><div>Advance Paid: ₹{{paid_amount}}</div><div>Balance Due: ₹{{balance_due}}</div><hr/><div style='font-size: 10px;'>* Customer acknowledges data backup disclaimer.<br/>* 30-day pickup policy applies.</div></div>",
                "variables": ["company_name", "ticket_number", "created_at", "brand_model", "imei_serial_no", "defect_name", "total_amount", "paid_amount", "balance_due"]
            }
        ]
    },

    "hvac_tailoring": {
        "key": "hvac_tailoring",
        "name": "HVAC / Tailoring & Custom Orders",
        "icon": "Wind",
        "tagline": "Air conditioning installation & ducting, or bespoke tailoring & alteration craft",
        "description": "Multi-purpose preset for dimension-based businesses (Tonnage/Inches, fabric/refrigerant spec, on-site measurement visits, trial fittings, and alteration tracking).",
        "custom_fields": [
            {
                "entity": "ticket",
                "field_key": "service_mode",
                "name": "Service Category",
                "field_type": "dropdown",
                "required": True,
                "options": [
                    {"label": "HVAC - Split / Window AC Service", "value": "hvac_split_service"},
                    {"label": "HVAC - VRV / Ducting Installation", "value": "hvac_installation"},
                    {"label": "Tailoring - Bespoke Suit / Tuxedo", "value": "tailor_suit"},
                    {"label": "Tailoring - Traditional Dress / Saree Alteration", "value": "tailor_traditional"},
                    {"label": "Tailoring - Industrial Uniforms Batch", "value": "tailor_uniforms"}
                ],
                "sort_order": 1
            },
            {
                "entity": "ticket",
                "field_key": "spec_measurement_units",
                "name": "Capacity (Tons) / Garment Size (Inches)",
                "field_type": "number",
                "placeholder": "e.g. 1.5 or 38",
                "required": True,
                "sort_order": 2
            },
            {
                "entity": "ticket",
                "field_key": "refrigerant_or_fabric_type",
                "name": "Refrigerant Gas (R32/R410A) or Fabric Spec",
                "field_type": "short_text",
                "placeholder": "e.g. R32 Eco or Italian Wool Blend",
                "sort_order": 3
            },
            {
                "entity": "ticket",
                "field_key": "scheduled_visit_date",
                "name": "Installation / Trial Fitting Due Date",
                "field_type": "date_time",
                "required": True,
                "sort_order": 4
            },
            {
                "entity": "ticket",
                "field_key": "site_or_garment_photo",
                "name": "Site Layout / Garment Reference Image",
                "field_type": "image_upload",
                "sort_order": 5
            },
            {
                "entity": "ticket",
                "field_key": "customer_approval_sign",
                "name": "Measurement & Trial Approval Sign",
                "field_type": "signature_pad",
                "required": True,
                "sort_order": 6
            },
            {
                "entity": "ticket",
                "field_key": "special_instructions",
                "name": "Custom Fitting / Ducting Instructions",
                "field_type": "long_text",
                "placeholder": "e.g. 2-inch pipe extra length or slim-fit tapered trousers",
                "sort_order": 7
            }
        ],
        "pipeline": {
            "name": "HVAC & Custom Order Pipeline",
            "code": "hvac_custom_pipeline",
            "entity": "ticket",
            "description": "5-phase measurement, fabrication/execution, trial fitting, and final signoff",
            "statuses": [
                {"name": "Booking & Inquiries", "code": "booking", "bg_color": "#e0f2fe", "text_color": "#0369a1", "icon": "Calendar", "sort_order": 1, "is_initial": True},
                {"name": "Site Visit / Measurements Taken", "code": "measurement", "bg_color": "#fef3c7", "text_color": "#92400e", "icon": "Ruler", "sort_order": 2},
                {"name": "Cutting / Fabrication / Piping In Progress", "code": "fabrication", "bg_color": "#fed7aa", "text_color": "#9a3412", "icon": "Scissors", "sort_order": 3},
                {"name": "Trial Fitting / Commissioning Run", "code": "trial_fitting", "bg_color": "#f3e8ff", "text_color": "#7e22ce", "icon": "Sparkles", "sort_order": 4},
                {"name": "Final Finishing & Ready", "code": "ready", "bg_color": "#bbf7d0", "text_color": "#15803d", "icon": "CheckCircle", "sort_order": 5},
                {"name": "Order Completed & Delivered", "code": "delivered", "bg_color": "#15803d", "text_color": "#ffffff", "icon": "Smile", "sort_order": 6, "is_terminal": True}
            ],
            "transitions": [
                {"from_code": "booking", "to_code": "measurement", "name": "Schedule Site Visit / Measure", "guards": {}, "event_hooks": {"auto_create_task": {"enabled": True, "title": "Take site measurements / size chart", "assignee_role": "technician"}}},
                {"from_code": "measurement", "to_code": "fabrication", "name": "Start Execution", "guards": {}, "event_hooks": {}},
                {"from_code": "fabrication", "to_code": "trial_fitting", "name": "Call Customer for Trial", "guards": {}, "event_hooks": {"send_sms": {"enabled": True, "template": "Your order #{{ticket_number}} is ready for trial fitting on {{scheduled_visit_date}}."}}},
                {"from_code": "trial_fitting", "to_code": "ready", "name": "Trial Approved", "guards": {}, "event_hooks": {}},
                {"from_code": "ready", "to_code": "delivered", "name": "Final Handover", "guards": {"closure_gate": True}, "event_hooks": {"send_sms": {"enabled": True, "template": "Order #{{ticket_number}} complete. Thank you for your business!"}}}
            ]
        },
        "handbooks": [
            {
                "code": "brands_models",
                "name": "HVAC / Fabric Equipment Brands",
                "is_hierarchical": True,
                "items": [
                    {"code": "daikin", "name": "Daikin AC", "children": [
                        {"code": "dk_ftkf", "name": "FTKF 1.5 Ton Inverter"},
                        {"code": "dk_vrv", "name": "VRV-X Central System"}
                    ]},
                    {"code": "voltas", "name": "Voltas", "children": [
                        {"code": "vol_mha", "name": "Maha Adjustable Inverter AC"},
                        {"code": "vol_cassette", "name": "Commercial Cassette 3 Ton"}
                    ]},
                    {"code": "raymond", "name": "Raymond Bespoke Fabrics", "children": [
                        {"code": "ray_wool", "name": "Super 120s Pure Wool"},
                        {"code": "ray_linen", "name": "Irish Pure Linen"}
                    ]}
                ]
            },
            {
                "code": "defect_codes",
                "name": "Service & Alteration Types",
                "is_hierarchical": True,
                "items": [
                    {"code": "hvac_issues", "name": "HVAC Cooling & Gas Faults", "children": [
                        {"code": "gas_charging", "name": "Refrigerant R32 Top-up & Nitrogen Leak Test", "extra_data": {"labels": {"hi": "गैस रीफिल", "en": "Gas Refill"}}},
                        {"code": "jet_pump_wash", "name": "Indoor & Outdoor Jet Pump Deep Wash", "extra_data": {"labels": {"hi": "जेट पम्प सर्विस", "en": "Jet Wash"}}}
                    ]},
                    {"code": "tailoring_alterations", "name": "Garment Alteration Codes", "children": [
                        {"code": "waist_tapering", "name": "Trouser Waist & Inseam Tapering", "extra_data": {"labels": {"hi": "कमर साइजिंग", "en": "Waist Tapering"}}},
                        {"code": "shoulder_pad_align", "name": "Suit Shoulder Pad & Armhole Restitching", "extra_data": {"labels": {"hi": "कंधा फिटिंग", "en": "Shoulder Fit"}}}
                    ]}
                ]
            },
            {
                "code": "units",
                "name": "Measurement Units",
                "is_hierarchical": False,
                "items": [
                    {"code": "ton", "name": "Tons (TR)"},
                    {"code": "meter", "name": "Meters (Mtr)"},
                    {"code": "inch", "name": "Inches (In)"},
                    {"code": "suit", "name": "Full Suit (Set)"},
                    {"code": "pcs", "name": "Pieces (Pcs)"}
                ]
            },
            {
                "code": "payment_tags",
                "name": "Payment Types",
                "is_hierarchical": False,
                "items": [
                    {"code": "advance_cash", "name": "50% Booking Advance"},
                    {"code": "upi", "name": "UPI Payment"},
                    {"code": "bank_transfer", "name": "Bank Transfer"}
                ]
            },
            {
                "code": "expense_categories",
                "name": "Materials & Subcontractor Expenses",
                "is_hierarchical": False,
                "items": [
                    {"code": "copper_piping", "name": "Copper Piping & Foam Insulation"},
                    {"code": "lining_buttons", "name": "Silk Lining, Zippers & Horn Buttons"},
                    {"code": "freon_gas", "name": "R32 / R410A Refrigerant Cylinders"}
                ]
            }
        ],
        "catalog_items": [
            {"name": "Complete Jet Pump AC Servicing (Split)", "sku": "SRV-JET-SPLIT", "rate": 999.0, "type": "service"},
            {"name": "Bespoke 2-Piece Suit Tailoring (Labor)", "sku": "SRV-SUIT-2PC", "rate": 5500.0, "type": "service"}
        ],
        "templates": [
            {
                "name": "Measurement & Job Sheet (A4)",
                "type": "job_sheet",
                "paper_width": "A4",
                "html_body": "<div style='font-family: Arial, sans-serif; padding: 24px; border: 1px solid #94a3b8;'><div style='text-align: center;'><h2>{{company_name}} - SPECIFICATION SLIP</h2><p>Job #: {{ticket_number}} | Date: {{created_at}}</p></div><hr/><div><b>Customer:</b> {{customer_name}} ({{customer_phone}})<br/><b>Service Mode:</b> {{service_mode}}<br/><b>Capacity / Dimension:</b> {{spec_measurement_units}}<br/><b>Material Spec:</b> {{refrigerant_or_fabric_type}}<br/><b>Fitting Due Date:</b> {{scheduled_visit_date}}</div><hr/><div style='margin-top: 10px;'><b>Instructions:</b><p>{{special_instructions}}</p></div></div>",
                "variables": ["company_name", "ticket_number", "created_at", "customer_name", "customer_phone", "service_mode", "spec_measurement_units", "refrigerant_or_fabric_type", "scheduled_visit_date", "special_instructions"]
            }
        ]
    }
}
