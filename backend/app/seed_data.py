"""Seed dataset aligned with the SIH26099 problem statement.

Includes the exact cotton examples from the PDF (BLT-00123 / FAST-8871 /
MEC-4458 hex bolt trio), the safety near-miss valve example (PN16 vs PN25),
the NMC example records (CPCL-BLT-101, PWR-HW-8432, STL-BC-0192) and a
variety of engineering items across CPSEs with purchase history so the
savings dashboard has real numbers.
"""

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import CPSE, Material, Procurement
from .services import workflow

logger = logging.getLogger(__name__)

CPSE_LIST = [
    ("Chennai Petroleum Corporation Limited", "CPCL", "Petroleum & Gas"),
    ("NTPC Limited", "NTPC", "Power"),
    ("Steel Authority of India Limited", "SAIL", "Steel"),
    ("Oil and Natural Gas Corporation", "ONGC", "Oil & Gas"),
    ("Bharat Heavy Electricals Limited", "BHEL", "Power Equipment"),
    ("Coal India Limited", "CIL", "Coal"),
]

DEFAULT_UNIT = "nos"

# (cpse_short, legacy_code, description, raw_unit, manufacturer, part_number, procurements[(year,qty,price)])
MATERIALS = [
    # ---- The PDF bolt trio (CPSE A/B/C) ----
    ("CPCL", "BLT-00123", "Hex bolt M12 x 50, SS304", DEFAULT_UNIT, "", "", [(2024, 2000, 8.5)]),
    ("NTPC", "FAST-8871", "Bolt, hex head, 12 mm, 50 mm length, stainless steel 304", DEFAULT_UNIT, "", "", [(2024, 1500, 11.0)]),
    ("SAIL", "MEC-4458", "SS-304 hexagonal bolt, M12, L=50 mm", DEFAULT_UNIT, "", "", [(2024, 1200, 14.2)]),
    # ---- PDF Example Output three rows ----
    ("CPCL", "CPCL-BLT-101", "Hex bolt SS304 M12 x 50", DEFAULT_UNIT, "", "", [(2023, 900, 7.9)]),
    ("NTPC", "PWR-HW-8432", "Stainless steel hex bolt, 12 mm, 50 mm", DEFAULT_UNIT, "", "", [(2023, 1100, 10.4)]),
    ("SAIL", "STL-BC-0192", "Bolt hexagonal M12 L50 SS 304", DEFAULT_UNIT, "", "", [(2023, 800, 13.0)]),
    # ---- PDF NLP example: ball valve ----
    ("CPCL", "VALVE-BALL-2-CL150", "VALVE BALL 2IN CL150 SS316 FLANGED ASTM A351", DEFAULT_UNIT, "", "", [(2024, 60, 18500.0)]),
    ("ONGC", "BLV-2-150-SS316", "Ball valve 2 inch, 150 lb class, SS 316, flanged ends, ASTM A351", DEFAULT_UNIT, "", "", [(2024, 45, 21600.0)]),
    ("NTPC", "BVL-150-221", "Ball valve SS316 2 inch CL150 flanged", DEFAULT_UNIT, "", "", [(2024, 50, 19800.0)]),
    # ---- Safety near-miss: must NOT auto-merge ----
    ("CPCL", "BALL-VALVE-PN16-88", "Ball valve SS304, 2 inch, PN16", DEFAULT_UNIT, "", "", [(2024, 70, 9200.0)]),
    ("NTPC", "PIC-BV-PN25-12", "Ball valve SS304, 2 inch, PN25", DEFAULT_UNIT, "", "", [(2024, 80, 14300.0)]),
    # ---- Bearings ----
    ("CPCL", "BRG-6205-SKF", "BRG 6205 SKF", DEFAULT_UNIT, "SKF", "6205", [(2024, 400, 650.0)]),
    ("ONGC", "BEAR-6205-1", "Deep groove ball bearing 6205 SKF", DEFAULT_UNIT, "SKF", "6205", [(2024, 300, 720.0)]),
    ("NTPC", "BR-6205-ZZ", "Bearing 6205 ZZ SKF", DEFAULT_UNIT, "SKF", "6205-2RS1", [(2024, 350, 780.0)]),
    # ---- Cables ----
    ("CPCL", "CBL-PVC-4SQ", "PVC insulated copper cable 4 sq mm 1100V", DEFAULT_UNIT, "", "", [(2024, 5000, 42.0)]),
    ("NTPC", "WIRE-4SQ-PVC", "Cable, PVC insulated, 4 sq mm, 1.1 kV", DEFAULT_UNIT, "", "", [(2024, 4500, 46.0)]),
    ("SAIL", "PVC-CABLE-4MM", "4 sqmm PVC cable copper 1100 volts", DEFAULT_UNIT, "", "", [(2024, 3000, 44.5)]),
    ("NTPC", "XLPE-3C-50", "XLPE cable 3 core 50 sq mm 1.1 kV armoured", "m", "", "", [(2024, 1200, 385.0)]),
    ("BHEL", "CBL-XLPE-3CX50", "XLPE ARMOURED CABLE 3CX50SQMM 1.1KV", "m", "", "", [(2024, 900, 412.0)]),
    # ---- Pipes ----
    ("CPCL", "PIPE-GI-25", "GI pipe 25 mm NB medium class", "m", "", "", [(2024, 3000, 210.0)]),
    ("ONGC", "MS-PIPE-1IN", "Mild steel pipe 1 inch NB medium", "m", "", "", [(2024, 2500, 240.0)]),
    ("SAIL", "SMLS-PIPE-25", "Seamless carbon steel pipe 25 NB schedule 40", "m", "", "", [(2024, 1000, 385.0)]),
    # ---- Flanges ----
    ("CPCL", "FLG-SO-DN80-PN16", "Slip on flange DN80 PN16 SS316", DEFAULT_UNIT, "", "", [(2024, 500, 1250.0)]),
    ("ONGC", "FL816-80", "Flange SO 80NB 16bar SS316", DEFAULT_UNIT, "", "", [(2024, 400, 1330.0)]),
    # ---- Gaskets ----
    ("CPCL", "GSK-SW-DN80", "Spiral wound gasket DN80 CL150 SS316", DEFAULT_UNIT, "", "", [(2024, 600, 480.0)]),
    ("NTPC", "GSK-80-150", "Spiral wound gasket 80NB 150 lbs SS316", DEFAULT_UNIT, "", "", [(2024, 550, 520.0)]),
    # ---- Gate valves ----
    ("CPCL", "GATE-6-CL150", "Gate valve 6 inch CL150 carbon steel flanged", DEFAULT_UNIT, "", "", [(2024, 40, 24500.0)]),
    ("NTPC", "GTV-150-6", "Gate valve 150 lb 6 inch carbon steel", DEFAULT_UNIT, "", "", [(2024, 30, 26100.0)]),
    # ---- Motors ----
    ("CPCL", "MOTOR-5HP-415", "Electric motor 5 HP 3 phase 415V 1500 rpm TEFC", DEFAULT_UNIT, "", "", [(2024, 25, 38500.0)]),
    ("NTPC", "EM-5-415", "Motor 3 phase 5 HP 415V flange mounted", DEFAULT_UNIT, "", "", [(2024, 18, 40200.0)]),
    # ---- Welding electrodes ----
    ("CPCL", "ELEC-E7018-4", "Welding electrode E7018 4 mm", "kg", "", "", [(2024, 1500, 165.0)]),
    ("SAIL", "ROD-E7018-4MM", "E7018 welding rods 4 mm", "kg", "", "", [(2024, 1200, 172.0)]),
    # ---- Pumps ----
    ("CPCL", "CWP-100-25", "Centrifugal pump 100 m3/hr 25 m head", DEFAULT_UNIT, "", "", [(2024, 6, 485000.0)]),
    ("ONGC", "PUMP-CENT-100", "Centrifugal pump, capacity 100 cum/hr, head 25 m", DEFAULT_UNIT, "", "", [(2024, 4, 512000.0)]),
    # ---- Lubricants ----
    ("CPCL", "OIL-TO-32", "Transformer oil viscosity 32 grade I", "l", "", "", [(2024, 8000, 145.0)]),
    ("BHEL", "TR-OIL-32", "Transformer oil IS 335 grade 32", "l", "", "", [(2024, 6500, 152.0)]),
    # ---- Lighting ----
    ("CPCL", "LED-TUBE-20", "LED tube light 20 W 4 ft", DEFAULT_UNIT, "", "", [(2024, 3000, 260.0)]),
    ("NTPC", "TUBE-LED-20-4FT", "Tube light LED 20 watt 4 feet", DEFAULT_UNIT, "", "", [(2024, 2200, 285.0)]),
    # ---- Belts ----
    ("SAIL", "CONV-BELT-600", "Conveyor belt 600 mm width EP500", "m", "", "", [(2024, 800, 2100.0)]),
    ("CIL", "BELT-EP500-600", "CONVEYOR BELTING EP500 600MM", "m", "", "", [(2024, 700, 2250.0)]),
    # ---- Fasteners: nuts & washers & studs ----
    ("CPCL", "NUT-M12-SS304", "M12 nut stainless steel 304", DEFAULT_UNIT, "", "", [(2024, 4000, 3.5)]),
    ("SAIL", "SS-NUT-M12", "Stainless steel nut M12", DEFAULT_UNIT, "", "", [(2024, 3600, 3.9)]),
    ("CPCL", "WSH-M12-SS304", "Plain washer M12 SS304", DEFAULT_UNIT, "", "", [(2024, 4000, 1.8)]),
    ("NTPC", "STUD-M16X100", "Stud bolt M16 x 100 SS304 ASTM A193 B8", DEFAULT_UNIT, "", "", [(2024, 900, 65.0)]),
    ("CPCL", "STUD-A193-B8", "STUD BOLT A193 B8 M16 X 100", DEFAULT_UNIT, "", "", [(2024, 800, 70.0)]),
    # ---- Instruments ----
    ("CPCL", "PRES-GAUGE-100", "Pressure gauge 100 mm dia 0-16 bar bottom entry", DEFAULT_UNIT, "", "", [(2024, 300, 950.0)]),
    ("ONGC", "PG-100-16B", "Pressure gauge dial 100mm 0-16 bar lower mount", DEFAULT_UNIT, "", "", [(2024, 250, 1010.0)]),
]


def seed(db: Session, rerun: bool = False) -> dict:
    if not rerun:
        existing = db.query(func.count(CPSE.id)).scalar()
        if existing and existing > 0:
            return {"status": "already_seeded", "materials": db.query(func.count(Material.id)).scalar()}

    # CPSEs
    cpses = {}
    for name, short, sector in CPSE_LIST:
        cp = CPSE(name=name, short_name=short, sector=sector)
        db.add(cp)
        db.flush()
        cpses[short] = cp

    # materials + procurements
    count = 0
    lookup = {}
    for short, code, desc, unit, mfr, pn, procs in MATERIALS:
        mat = Material(
            cpse_id=cpses[short].id,
            legacy_code=code,
            raw_description=desc,
            raw_unit=unit,
            manufacturer=mfr,
            part_number=pn,
            source_file="seed-data (CPSE ERP extracts)",
            status="ingested",
        )
        db.add(mat)
        db.flush()
        lookup[code] = mat
        for year, qty, price in procs:
            db.add(
                Procurement(
                    material_id=mat.id,
                    year=year,
                    quantity=qty,
                    unit_price=price,
                    currency="INR",
                )
            )
        count += 1

    db.commit()

    # process each record (normalize + extract) then generate candidates
    llm = get_llm()
    materials = db.query(Material).all()
    for mat in materials:
        workflow.process_record(db, mat, llm)
    db.commit()

    created = workflow.run_matching_candidates(db, llm)
    logger.info("seed complete: %d materials, %d candidates (%s)", count, created, llm.mode)
    return {"status": "seeded", "materials": count, "candidates": created, "llm_mode": llm.mode}


from .llm.provider import get_llm  # noqa: E402