from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os

# Initialize Flask App
app = Flask(__name__)

# Database Setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define Database Model
class ICD(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    disease_chapter = db.Column(db.String(255), nullable=False)
    disease_group = db.Column(db.String(255), nullable=True)
    disease_name = db.Column(db.String(255), nullable=False)
    disease_code = db.Column(db.String(50), nullable=False)

class XN(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    xn_chapter = db.Column(db.String(50), nullable=False)
    xn_group = db.Column(db.String(255), nullable=False)
    xn_name = db.Column(db.String(255), nullable=False)
    xn_occurence = db.Column(db.Integer, nullable=True)

# Define Cartesian Product Table (ICD_XN)
class ICD_XN(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    icd_id = db.Column(db.Integer, db.ForeignKey('icd.id'), nullable=False)
    xn_id = db.Column(db.Integer, db.ForeignKey('xn.id'), nullable=False)
    status = db.Column(db.String(50), default="Unknown")  # New column
    finalized = db.Column(db.String(50), default="Not Yet")  # New column

    # Relationships
    icd = db.relationship("ICD", backref=db.backref("icd_xn", cascade="all, delete-orphan"))
    xn = db.relationship("XN", backref=db.backref("icd_xn", cascade="all, delete-orphan"))

# Function to Initialize Database and Populate Cartesian Product
def initialize_database():
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
        # Check if Cartesian product already exists to prevent duplication
        if ICD_XN.query.first() is None:
            all_icds = ICD.query.all()
            all_xns = XN.query.all()

            # Insert Cartesian Product
            for icd in all_icds:
                for xn in all_xns:
                    new_entry = ICD_XN(
                        icd_id=icd.id,
                        xn_id=xn.id,
                        status="Unknown",  # Default value
                        finalized="Not Yet"  # Default value
                    )
                    db.session.add(new_entry)

            db.session.commit()
            print("✅ Cartesian product initialized successfully with default values!")

# Initialize the database automatically when the app starts
initialize_database()

# Home Route - Load Disease Chapters
@app.route('/')
def index():
    disease_chapters = db.session.query(ICD.disease_chapter).distinct().all()
    grouped_data = db.session.query(
        ICD.disease_name,
        db.func.group_concat(XN.xn_name, ', ')  # Combine test names into one column
    ).join(ICD_XN, ICD.id == ICD_XN.icd_id) \
     .join(XN, ICD_XN.xn_id == XN.id) \
     .filter(ICD_XN.status == 'Used') \
     .group_by(ICD.disease_name) \
     .all()
    return render_template('index.html', disease_chapters=[dc[0] for dc in disease_chapters], grouped_data=grouped_data)
# Route for Searching by Disease Chapter
@app.route('/chapter')
def chapter():
    disease_chapters = db.session.query(ICD.disease_chapter).distinct().all()
    return render_template('chapter.html', disease_chapters=[dc[0] for dc in disease_chapters])

# Route for Searching by Disease Group
@app.route('/group')
def group():
    disease_groups = db.session.query(ICD.disease_group).distinct().all()
    return render_template('group.html', disease_groups=[dg[0] for dg in disease_groups])

# Route for Searching by Disease Name
@app.route('/name')
def name():
    disease_names = db.session.query(ICD.disease_name).distinct().all()
    return render_template('name.html', disease_names=[dn[0] for dn in disease_names])

# Route to Fetch Tests from XN Table
@app.route('/get_tests', methods=['GET'])
def get_tests():
    tests = XN.query.all()
    
    if not tests:
        return jsonify({"error": "No tests found"}), 404

    test_list = [
        {"id": t.id, "XN Chapter": t.xn_chapter, "XN Group": t.xn_group, "XN Name": t.xn_name, "XN Occurence": t.xn_occurence}
        for t in tests
    ]

    return jsonify(test_list)

@app.route('/get_common_xns', methods=['POST'])
def get_common_xns():
    data = request.get_json()
    selected_chapter = data.get("chapter")

    if not selected_chapter:
        return jsonify({"tests": "No chapter selected"})  # Return empty response if no chapter is selected

    with app.app_context():
        # Get all ICD IDs for the selected chapter
        icds = ICD.query.filter_by(disease_chapter=selected_chapter).all()
        icd_ids = [icd.id for icd in icds]

        if not icd_ids:
            return jsonify({"tests": "No diseases found in this chapter"})

        # Find tests that are common across all diseases in this chapter
        common_xns_query = db.session.query(
            XN.xn_name
        ).join(ICD_XN, XN.id == ICD_XN.xn_id) \
         .filter(ICD_XN.icd_id.in_(icd_ids), ICD_XN.status == 'Used') \
         .group_by(XN.xn_name) \
         .having(db.func.count(ICD_XN.icd_id) == len(icd_ids)) \
         .all()

        # Extract test names
        common_xns = [row[0] for row in common_xns_query]

        return jsonify({"tests": ', '.join(common_xns) if common_xns else "No common tests found"})

@app.route('/remove_xn_from_chapter', methods=['POST'])
def remove_xn_from_chapter():
    data = request.get_json()
    selected_chapter = data.get("chapter")
    xn_name_to_remove = data.get("xn_name")

    if not selected_chapter or not xn_name_to_remove:
        return jsonify({"message": "Invalid data received"}), 400

    with app.app_context():
        # Get all ICD IDs under the selected chapter
        icds = ICD.query.filter_by(disease_chapter=selected_chapter).all()
        icd_ids = [icd.id for icd in icds]

        if not icd_ids:
            return jsonify({"message": "No diseases found for this chapter"}), 400

        # Find the XN ID that matches the given test name
        xn = XN.query.filter_by(xn_name=xn_name_to_remove).first()
        if not xn:
            return jsonify({"message": "Test not found"}), 400

        # Update the ICD_XN table: Set status back to 'Unknown' where status is 'Used'
        updated_records = ICD_XN.query.filter(
            ICD_XN.icd_id.in_(icd_ids),
            ICD_XN.xn_id == xn.id,
            ICD_XN.status == 'Used'
        ).all()

        if not updated_records:
            return jsonify({"message": "No matching records found"}), 400

        for record in updated_records:
            record.status = "Unknown"

        db.session.commit()

    return jsonify({"message": f"Test '{xn_name_to_remove}' removed from chapter '{selected_chapter}'!"})

#for group
@app.route('/get_common_xns_group', methods=['POST'])
def get_common_xns_group():
    data = request.get_json()
    selected_group = data.get("group")

    if not selected_group:
        return jsonify({"tests": "No group selected"})  # Return empty response if no chapter is selected

    with app.app_context():
        # Get all ICD IDs for the selected chapter
        icds = ICD.query.filter_by(disease_group=selected_group).all()
        icd_ids = [icd.id for icd in icds]

        if not icd_ids:
            return jsonify({"tests": "No diseases found in this chapter"})

        # Find tests that are common across all diseases in this chapter
        common_xns_query = db.session.query(
            XN.xn_name
        ).join(ICD_XN, XN.id == ICD_XN.xn_id) \
         .filter(ICD_XN.icd_id.in_(icd_ids), ICD_XN.status == 'Used') \
         .group_by(XN.xn_name) \
         .having(db.func.count(ICD_XN.icd_id) == len(icd_ids)) \
         .all()

        # Extract test names
        common_xns = [row[0] for row in common_xns_query]

        return jsonify({"tests": ', '.join(common_xns) if common_xns else "No common tests found"})

@app.route('/remove_xn_from_group', methods=['POST'])
def remove_xn_from_group():
    data = request.get_json()
    selected_group = data.get("group")
    xn_name_to_remove = data.get("xn_name")

    if not selected_group or not xn_name_to_remove:
        return jsonify({"message": "Invalid data received"}), 400

    with app.app_context():
        # Get all ICD IDs under the selected chapter
        icds = ICD.query.filter_by(disease_chapter=selected_group).all()
        icd_ids = [icd.id for icd in icds]

        if not icd_ids:
            return jsonify({"message": "No diseases found for this group"}), 400

        # Find the XN ID that matches the given test name
        xn = XN.query.filter_by(xn_name=xn_name_to_remove).first()
        if not xn:
            return jsonify({"message": "Test not found"}), 400

        # Update the ICD_XN table: Set status back to 'Unknown' where status is 'Used'
        updated_records = ICD_XN.query.filter(
            ICD_XN.icd_id.in_(icd_ids),
            ICD_XN.xn_id == xn.id,
            ICD_XN.status == 'Used'
        ).all()

        if not updated_records:
            return jsonify({"message": "No matching records found"}), 400

        for record in updated_records:
            record.status = "Unknown"

        db.session.commit()

    return jsonify({"message": f"Test '{xn_name_to_remove}' removed from group '{selected_group}'!"})

@app.route('/get_selected_xns', methods=['POST'])
def get_selected_xns():
    data = request.get_json()
    selected_chapter = data.get("chapter")

    if not selected_chapter:
        return jsonify([])  # Return empty list if no chapter is selected

    with app.app_context():
        # Get all ICDs under the selected chapter
        icds = ICD.query.filter_by(disease_chapter=selected_chapter).all()
        icd_ids = [icd.id for icd in icds]

        if not icd_ids:
            return jsonify([])  # No ICDs found

        # Get all XNs associated with the selected ICDs where `status = 'Used'`
        results = db.session.query(
            ICD.disease_name,
            db.func.group_concat(XN.xn_name, ', ')
        ).join(ICD_XN, ICD.id == ICD_XN.icd_id) \
         .join(XN, ICD_XN.xn_id == XN.id) \
         .filter(ICD_XN.icd_id.in_(icd_ids), ICD_XN.status == 'Used') \
         .group_by(ICD.disease_name) \
         .all()

        # Convert to JSON format
        selected_xns = [{"disease": disease, "tests": tests} for disease, tests in results]

    return jsonify(selected_xns)


@app.route('/update_icd_xn', methods=['POST'])
def update_icd_xn():
    data = request.get_json()
    selected_chapter = data.get("chapter")
    selected_tests = data.get("test_ids")

    if not selected_chapter or not selected_tests:
        return jsonify({"message": "Invalid data received"}), 400

    with app.app_context():
        # Find all ICDs with the selected chapter
        icds = ICD.query.filter_by(disease_chapter=selected_chapter).all()
        icd_ids = [icd.id for icd in icds]

        if not icd_ids:
            return jsonify({"message": "No diseases found for this chapter"}), 400

        # Update the `ICD_XN` table where ICD matches selected chapter and XN matches selected tests
        icd_xn_records = ICD_XN.query.filter(ICD_XN.icd_id.in_(icd_ids), ICD_XN.xn_id.in_(selected_tests)).all()

        if not icd_xn_records:
            return jsonify({"message": "No matching ICD-XN records found"}), 400

        # Update status to 'Used'
        for record in icd_xn_records:
            record.status = "Used"

        db.session.commit()

    return jsonify({"message": "ICD-XN table updated successfully!"})
@app.route('/update_icd_xn_group', methods=['POST'])
def update_icd_xn_group():
    data = request.get_json()
    selected_group = data.get("group")  # Get the selected disease group
    selected_tests = data.get("test_ids")  # Get selected test IDs

    if not selected_group or not selected_tests:
        return jsonify({"message": "Invalid data received"}), 400

    with app.app_context():
        # Find all ICDs with the selected disease group
        icds = ICD.query.filter_by(disease_group=selected_group).all()
        icd_ids = [icd.id for icd in icds]

        if not icd_ids:
            return jsonify({"message": "No diseases found for this group"}), 400

        # Update the `ICD_XN` table where ICD matches selected group and XN matches selected tests
        icd_xn_records = ICD_XN.query.filter(ICD_XN.icd_id.in_(icd_ids), ICD_XN.xn_id.in_(selected_tests)).all()

        if not icd_xn_records:
            return jsonify({"message": "No matching ICD-XN records found"}), 400

        # Update status to 'Used'
        for record in icd_xn_records:
            record.status = "Used"

        db.session.commit()

    return jsonify({"message": "ICD-XN table updated successfully for the selected disease group!"})

#for name
@app.route('/get_xns_for_disease', methods=['POST'])
def get_xns_for_disease():
    data = request.get_json()
    selected_disease = data.get("name")

    if not selected_disease:
        return jsonify({"tests": "No disease selected"}), 400

    with app.app_context():
        # Get the ICD ID for the selected disease
        icd = ICD.query.filter_by(disease_name=selected_disease).first()
        if not icd:
            return jsonify({"tests": "Disease not found"}), 400

        # Find all XNs linked to this disease where status = 'Used'
        associated_xns = db.session.query(
            XN.xn_name
        ).join(ICD_XN, XN.id == ICD_XN.xn_id) \
         .filter(ICD_XN.icd_id == icd.id, ICD_XN.status == 'Used') \
         .all()

        # Extract test names
        xns_list = [row[0] for row in associated_xns]

        return jsonify({"tests": xns_list if xns_list else "No associated tests found"})

@app.route('/update_icd_xn_name', methods=['POST'])
def update_icd_xn_name():
    data = request.get_json()
    selected_name = data.get("name")  # Get the selected disease name
    selected_tests = data.get("test_ids")  # Get selected test IDs

    if not selected_name or not selected_tests:
        return jsonify({"message": "Invalid data received"}), 400

    with app.app_context():
        # Find the ICD entry with the selected disease name
        icd = ICD.query.filter_by(disease_name=selected_name).first()

        if not icd:
            return jsonify({"message": "No matching disease found for this name"}), 400

        # Update the `ICD_XN` table where ICD matches selected name and XN matches selected tests
        icd_xn_records = ICD_XN.query.filter(ICD_XN.icd_id == icd.id, ICD_XN.xn_id.in_(selected_tests)).all()

        if not icd_xn_records:
            return jsonify({"message": "No matching ICD-XN records found"}), 400

        # Update status to 'Used'
        for record in icd_xn_records:
            record.status = "Used"

        db.session.commit()

    return jsonify({"message": f"ICD-XN table updated successfully for {selected_name}!"})


@app.route('/remove_xn_from_disease', methods=['POST'])
def remove_xn_from_disease():
    data = request.get_json()
    selected_disease = data.get("name")
    xn_name_to_remove = data.get("xn_name")

    if not selected_disease or not xn_name_to_remove:
        return jsonify({"message": "Invalid data received"}), 400

    with app.app_context():
        # Find the ICD ID based on disease name
        icd = ICD.query.filter_by(disease_name=selected_disease).first()
        if not icd:
            return jsonify({"message": "Disease not found"}), 400

        # Find the XN ID based on test name
        xn = XN.query.filter_by(xn_name=xn_name_to_remove).first()
        if not xn:
            return jsonify({"message": "Test not found"}), 400

        # Find all matching records in ICD_XN where status is 'Used'
        updated_records = ICD_XN.query.filter(
            ICD_XN.icd_id == icd.id,
            ICD_XN.xn_id == xn.id,
            ICD_XN.status == 'Used'
        ).all()

        if not updated_records:
            return jsonify({"message": "No matching records found"}), 400

        # Update status back to 'Unknown'
        for record in updated_records:
            record.status = "Unknown"

        db.session.commit()

    return jsonify({"message": f"Test '{xn_name_to_remove}' removed from '{selected_disease}'!"})

import pandas as pd
from flask import send_file

@app.route('/export_icd_xn/<file_format>', methods=['GET'])
def export_icd_xn(file_format):
    with app.app_context():
        # Fetch all data from the ICD_XN table
        records = db.session.query(
            ICD_XN.id, 
            ICD.disease_name, 
            XN.xn_name, 
            ICD_XN.status, 
            ICD_XN.finalized
        ).join(ICD, ICD_XN.icd_id == ICD.id) \
         .join(XN, ICD_XN.xn_id == XN.id) \
         .all()

        # Convert data to Pandas DataFrame
        df = pd.DataFrame(records, columns=["ID", "Disease Name", "Test Name", "Status", "Finalized"])

        # Define file path
        file_path = "exported_data.xlsx" if file_format == "xlsx" else "exported_data.csv"

        # Export to the selected format
        if file_format == "xlsx":
            df.to_excel(file_path, index=False)
        else:
            df.to_csv(file_path, index=False)

    return send_file(file_path, as_attachment=True)

# Run the App
if __name__ == '__main__':
    app.run(debug=True)
