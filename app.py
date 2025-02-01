from flask import Flask, render_template, request, redirect, url_for, send_file
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId

app = Flask(__name__)

try:
    # Connect to MongoDB
    client = MongoClient("mongodb+srv://preaditya123:Aditya%401735@cluster0.bu4lp.mongodb.net/pdf_database?retryWrites=true&w=majority&appName=Cluster0")
    db = client["pdf_database"]
    fs = GridFS(db)  # Initialize GridFS AFTER db is defined
    print("✅ MongoDB connected successfully!")
    
    # Define collections
    pdfs_collection = db["pdfs"]
    links_collection = db["links"]
    
except Exception as e:
    print("❌ Connection failed:", e)
    # Prevent application from running if connection fails
    raise SystemExit(e)

# Rest of your routes...

@app.route('/')
def index():
    pdfs = list(pdfs_collection.find({}))
    for pdf in pdfs:
        pdf["_id"] = str(pdf["_id"])
    return render_template("index.html", pdfs=pdfs)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file_name = request.form['file_name']
        file_links = request.form.getlist('file_link')
        uploaded_file = request.files.get('file_input')

        # Validate at least one link or file
        if not file_links and (not uploaded_file or uploaded_file.filename == ''):
            return "Error: At least one link or file is required", 400

        file_id = None
        if uploaded_file and uploaded_file.filename != '':
            file_id = fs.put(uploaded_file, filename=uploaded_file.filename)

        file_entry = {
            "name": file_name,
            "links": [link for link in file_links if link],
            "file_id": str(file_id) if file_id else None
        }

        pdfs_collection.insert_one(file_entry)
        return redirect(url_for('index'))
    
    return render_template("upload.html")

@app.route('/edit/<pdf_id>', methods=['GET', 'POST'])
def edit(pdf_id):
    pdf = pdfs_collection.find_one({"_id": ObjectId(pdf_id)})
    if not pdf:
        return "PDF not found", 404

    if request.method == 'POST':
        pdf_name = request.form['pdf_name']
        pdf_links = request.form.getlist('pdf_link')
        pdf_file = request.files.get('pdf_file')

        # Validate at least one link or file exists after update
        has_existing_file = bool(pdf.get('file_id'))
        new_file_provided = pdf_file and pdf_file.filename != ''
        has_links = bool([link for link in pdf_links if link])
        
        if not has_links and not new_file_provided and not has_existing_file:
            return "Error: At least one link or PDF file is required", 400

        updated_data = {
            "name": pdf_name,
            "links": [link for link in pdf_links if link]  # Filter empty links
        }

        # Handle file update
        if pdf_file and pdf_file.filename != '':
            # Delete old file if exists
            if pdf.get('file_id'):
                try:
                    fs.delete(ObjectId(pdf['file_id']))
                except:
                    pass
            # Store new file
            updated_data['file_id'] = str(fs.put(pdf_file, filename=pdf_file.filename))

        pdfs_collection.update_one(
            {"_id": ObjectId(pdf_id)},
            {"$set": updated_data}
        )
        return redirect(url_for('index'))

    # Convert ObjectId to string for template
    pdf['_id'] = str(pdf['_id'])
    return render_template("edit.html", pdf=pdf)

@app.route('/download/<file_id>')
def download(file_id):
    try:
        file_data = fs.get(ObjectId(file_id))
        return send_file(
            file_data,
            download_name=file_data.filename,
            as_attachment=True
        )
    except:
        return "File not found", 404

@app.route('/delete/<pdf_id>', methods=['POST'])
def delete(pdf_id):
    pdf = pdfs_collection.find_one({"_id": ObjectId(pdf_id)})
    if pdf and pdf.get('file_id'):
        try:
            fs.delete(ObjectId(pdf['file_id']))
        except:
            pass
    pdfs_collection.delete_one({"_id": ObjectId(pdf_id)})
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)