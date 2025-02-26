import pandas as pd
from app import db, app
from sqlalchemy import text

# Load Excel File
file_path = "ICD vs XN.xlsx"  # Change this if needed
df_icd = pd.read_excel(file_path, sheet_name="ICD")
df_xn = pd.read_excel(file_path, sheet_name="XN")

# Define Table Schema
with app.app_context():
    # Drop existing tables
    db.session.execute(text("DROP TABLE IF EXISTS icd;"))
    db.session.execute(text("DROP TABLE IF EXISTS xn;"))
    db.session.commit()

    # Recreate ICD Table
    db.session.execute(text("""
        CREATE TABLE icd (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disease_chapter TEXT,
            disease_group TEXT,
            disease_name TEXT,
            disease_code TEXT
        );
    """))

    # Recreate XN Table
    db.session.execute(text("""
        CREATE TABLE xn (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            xn_chapter TEXT,
            xn_group TEXT,
            xn_name TEXT,
            xn_occurence TEXT
        );
    """))
    db.session.commit()

    # Insert Data into ICD Table
    df_icd.to_sql("icd", con=db.engine, if_exists="append", index=False)

    # Insert Data into XN Table
    df_xn.to_sql("xn", con=db.engine, if_exists="append", index=False)

    print("✅ Data successfully imported!")
