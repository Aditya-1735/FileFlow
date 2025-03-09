from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId
import re
import os
from auth import auth, login_required, get_current_user
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__, static_folder='static')

# Set secret key from environment variable
app.secret_key = os.environ.get('SECRET_KEY')

# Register auth blueprint
app.register_blueprint(auth)

try:
    # Connect to MongoDB
    mongodb_uri = os.environ.get("MONGODB_URI")
    client = MongoClient(mongodb_uri)
    db = client["pdf_database"]
    fs = GridFS(db)
    pdfs_collection = db["pdfs"]
    folders_collection = db["folders"]
    print("✅ MongoDB connected successfully!")
    
except Exception as e:
    print("❌ Connection failed:", e)
    raise SystemExit(e)

# Add current_user to all templates
@app.context_processor
def inject_current_user():
    return {'current_user': get_current_user()}

@app.route('/')
@login_required
def index():
    # Get current user ID
    user_id = session.get('user_id')
    
    # Fetch all folders for this user or global folders
    folders = list(folders_collection.find({
        "$or": [
            {"user_id": user_id},
            {"is_global": True}
        ]
    }))
    for folder in folders:
        folder["_id"] = str(folder["_id"])
    
    # Fetch files without a specific folder
    search_query = request.args.get('search', '').strip()
    folder_id = request.args.get('folder', '').strip()
    
    # Base query for files
    query = {
        "$or": [
            {"user_id": user_id},
            {"is_global": True}
        ]
    }
    
    if search_query:
        query["name"] = {"$regex": f".*{re.escape(search_query)}.*", "$options": "i"}
    
    if folder_id:
        query["folder_id"] = folder_id
    else:
        query["folder_id"] = None
    
    pdfs = list(pdfs_collection.find(query))
    
    for pdf in pdfs:
        pdf["_id"] = str(pdf["_id"])
    
    return render_template("index.html", pdfs=pdfs, folders=folders)

@app.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    folder_name = request.form['folder_name']
    description = request.form.get('description', '').strip()
    user_id = session.get('user_id')
    is_global = request.form.get('is_global') == 'on'  # New field for global access
    
    # Validate folder name length
    if len(folder_name) > 15:
        flash("Folder name must be 15 characters or less", "error")
        return redirect(url_for('index'))
    
    # Validate description length
    if len(description) > 15:
        flash("Description must be 15 characters or less", "error")
        return redirect(url_for('index'))
    
    # Check if folder with same name already exists for this user
    existing_folder = folders_collection.find_one({"name": folder_name, "user_id": user_id})
    if existing_folder:
        flash("Folder with this name already exists", "error")
        return redirect(url_for('index'))
    
    folder_entry = {
        "name": folder_name,
        "description": description,
        "created_at": datetime.now(),
        "user_id": user_id,
        "is_global": is_global  # Add is_global field
    }
    
    result = folders_collection.insert_one(folder_entry)
    flash("Folder created successfully", "success")
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    user_id = session.get('user_id')
    
    # Fetch folders for dropdown (user's folders and global folders)
    folders = list(folders_collection.find({
        "$or": [
            {"user_id": user_id},
            {"is_global": True}
        ]
    }))
    
    if request.method == 'POST':
        file_name = request.form['file_name']
        description = request.form.get('description', '').strip()
        file_links = request.form.getlist('file_link')
        uploaded_file = request.files.get('file_input')
        folder_id = request.form.get('folder_id')
        is_global = request.form.get('is_global') == 'on'  # New field

        # Validate at least one link or file
        if not file_links and (not uploaded_file or uploaded_file.filename == ''):
            return "Error: At least one link or file is required", 400

        file_id = None
        if uploaded_file and uploaded_file.filename != '':
            file_id = fs.put(uploaded_file, filename=uploaded_file.filename)

        file_entry = {
            "name": file_name,
            "description": description,
            "links": [link for link in file_links if link],
            "file_id": str(file_id) if file_id else None,
            "folder_id": folder_id if folder_id else None,
            "user_id": user_id,  # Associate files with users
            "is_global": is_global  # Add is_global field
        }

        pdfs_collection.insert_one(file_entry)
        return redirect(url_for('index'))
    
    return render_template("upload.html", folders=folders)

@app.route('/edit_folder/<folder_id>', methods=['GET', 'POST'])
@login_required
def edit_folder(folder_id):
    try:
        user_id = session.get('user_id')
        folder = folders_collection.find_one({"_id": ObjectId(folder_id), "user_id": user_id})
        
        if not folder:
            flash("Folder not found or access denied", "error")
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            new_name = request.form['folder_name']
            new_description = request.form.get('description', '').strip()
            is_global = request.form.get('is_global') == 'on'  # Get global setting
            
            # Validate description length
            if len(new_description) > 15:
                flash("Description must be 15 characters or less", "error")
                return redirect(url_for('edit_folder', folder_id=folder_id))
            
            # Check if new name already exists (excluding current folder)
            existing_folder = folders_collection.find_one({
                "name": new_name, 
                "user_id": user_id,
                "_id": {"$ne": ObjectId(folder_id)}
            })
            
            if existing_folder:
                flash("A folder with this name already exists", "error")
                return redirect(url_for('edit_folder', folder_id=folder_id))
            
            # Update folder
            folders_collection.update_one(
                {"_id": ObjectId(folder_id), "user_id": user_id},
                {"$set": {
                    "name": new_name,
                    "description": new_description,
                    "is_global": is_global  # Update the is_global field
                }}
            )
            
            flash("Folder updated successfully", "success")
            return redirect(url_for('index'))
        
        # Convert ObjectId to string for template
        folder['_id'] = str(folder['_id'])
        return render_template("edit_folder.html", folder=folder)
    
    except Exception as e:
        # Print the actual error for debugging
        print(f"Error in edit_folder: {e}")
        flash(f"An unexpected error occurred", "error")
        return redirect(url_for('index'))

@app.route('/delete_folder/<folder_id>', methods=['POST'])
@login_required
def delete_folder(folder_id):
    try:
        user_id = session.get('user_id')
        
        # First, check if the folder belongs to the user
        folder = folders_collection.find_one({"_id": ObjectId(folder_id), "user_id": user_id})
        if not folder:
            flash("Folder not found or access denied", "error")
            return redirect(url_for('index'))
        
        # Check if folder has any files
        files_in_folder = pdfs_collection.count_documents({"folder_id": folder_id})
        
        if files_in_folder > 0:
            flash("Cannot delete folder. Remove files from this folder first.", "error")
            return redirect(url_for('index'))
        
        # Delete the folder
        result = folders_collection.delete_one({"_id": ObjectId(folder_id), "user_id": user_id})
        
        if result.deleted_count:
            flash("Folder deleted successfully", "success")
        else:
            flash("Folder not found", "error")
        
        return redirect(url_for('index'))
    
    except Exception as e:
        print(f"Error in delete_folder: {e}")
        flash("An unexpected error occurred", "error")
        return redirect(url_for('index'))

@app.route('/edit/<pdf_id>', methods=['GET', 'POST'])
@login_required
def edit(pdf_id):
    try:
        # Validate PDF ID format first
        pdf_id_obj = ObjectId(pdf_id)
    except InvalidId:
        flash("Invalid file ID format", "error")
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    try:
        # Fetch folders for dropdown (include both user and global folders)
        folders = list(folders_collection.find({
            "$or": [
                {"user_id": user_id},
                {"is_global": True}
            ]
        }))

        # Verify file belongs to user
        pdf = pdfs_collection.find_one({"_id": pdf_id_obj, "user_id": user_id})
        if not pdf:
            flash("File not found or access denied", "error")
            return redirect(url_for('index'))

        if request.method == 'POST':
            # Process form data with proper error handling
            try:
                pdf_name = request.form['pdf_name']
                description = request.form.get('description', '').strip()
                pdf_links = request.form.getlist('file_link')  # Fixed field name
                is_global = request.form.get('is_global') == 'on'  # Fixed field name
                folder_id = request.form.get('folder_id')
                
                # Validate folder if provided
                if folder_id:
                    try:
                        folder_id_obj = ObjectId(folder_id)
                        folder = folders_collection.find_one({
                            "_id": folder_id_obj,
                            "$or": [
                                {"user_id": user_id},
                                {"is_global": True}
                            ]
                        })
                        if not folder:
                            flash("Selected folder not found or access denied", "error")
                            return redirect(url_for('edit', pdf_id=pdf_id))
                    except InvalidId:
                        flash("Invalid folder ID format", "error")
                        return redirect(url_for('edit', pdf_id=pdf_id))

                # Validate required fields
                has_existing_file = bool(pdf.get('file_id'))
                has_links = any(link.strip() for link in pdf_links)
                new_file_provided = 'pdf_file' in request.files and request.files['pdf_file'].filename != ''

                if not has_links and not new_file_provided and not has_existing_file:
                    flash("Error: At least one link or PDF file is required", "error")
                    return redirect(url_for('edit', pdf_id=pdf_id))

                updated_data = {
                    "name": pdf_name,
                    "description": description,
                    "links": [link.strip() for link in pdf_links if link.strip()],
                    "folder_id": ObjectId(folder_id) if folder_id else None,
                    "is_global": is_global
                }

                # Handle file update
                if new_file_provided:
                    pdf_file = request.files['pdf_file']
                    try:
                        # Delete old file if exists
                        if pdf.get('file_id'):
                            try:
                                fs.delete(ObjectId(pdf['file_id']))
                            except Exception as e:
                                print(f"Error deleting old file: {e}")

                        # Store new file
                        file_id = fs.put(pdf_file, filename=pdf_file.filename)
                        updated_data['file_id'] = str(file_id)
                    except Exception as e:
                        print(f"Error handling file upload: {e}")
                        flash("Error uploading file. Please try again.", "error")
                        return redirect(url_for('edit', pdf_id=pdf_id))

                # Update database
                result = pdfs_collection.update_one(
                    {"_id": pdf_id_obj, "user_id": user_id},
                    {"$set": updated_data}
                )
                
                if result.modified_count == 1:
                    flash("File updated successfully", "success")
                else:
                    flash("No changes were made to the file", "info")
                    
                return redirect(url_for('index'))

            except KeyError as e:
                flash("Missing required field: " + str(e), "error")
                return redirect(url_for('edit', pdf_id=pdf_id))
            except Exception as e:
                print(f"Unexpected error during edit: {e}")
                flash("An error occurred while saving changes", "error")
                return redirect(url_for('edit', pdf_id=pdf_id))

        # Convert ObjectId to string for template
        pdf['_id'] = str(pdf['_id'])
        return render_template("edit.html", pdf=pdf, folders=folders)

    except Exception as e:
        print(f"Critical error in edit route: {e}")
        flash("A system error occurred. Please try again later.", "error")
        return redirect(url_for('index'))

@app.route('/download/<file_id>')
@login_required
def download(file_id):
    try:
        user_id = session.get('user_id')
        
        # Check if file belongs to user or is global
        pdf = pdfs_collection.find_one({
            "file_id": file_id,
            "$or": [
                {"user_id": user_id},
                {"is_global": True}
            ]
        })
        
        if not pdf:
            flash("File not found or access denied", "error")
            return redirect(url_for('index'))
            
        file_data = fs.get(ObjectId(file_id))
        return send_file(
            file_data,
            download_name=file_data.filename,
            as_attachment=True
        )
    except Exception as e:
        print(f"Error downloading file: {e}")
        flash("File not found or error during download", "error")
        return redirect(url_for('index'))

@app.route('/delete/<pdf_id>', methods=['POST'])
@login_required
def delete(pdf_id):
    try:
        user_id = session.get('user_id')
        
        # Verify file belongs to user
        pdf = pdfs_collection.find_one({"_id": ObjectId(pdf_id), "user_id": user_id})
        if not pdf:
            flash("File not found or access denied", "error")
            return redirect(url_for('index'))
        
        # Delete file from GridFS if it exists
        if pdf.get('file_id'):
            try:
                fs.delete(ObjectId(pdf['file_id']))
            except Exception as e:
                print(f"Error deleting file from GridFS: {e}")
        
        # Delete PDF document from collection
        result = pdfs_collection.delete_one({"_id": ObjectId(pdf_id), "user_id": user_id})
        
        if result.deleted_count:
            flash("File deleted successfully", "success")
        else:
            flash("File could not be deleted", "error")
            
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error deleting file: {e}")
        flash("An unexpected error occurred", "error")
        return redirect(url_for('index'))


from bson.errors import InvalidId

# Public folder view
@app.route('/public/folder/<folder_id>')
def public_folder_view(folder_id):
    try:
        folder = folders_collection.find_one({
            "_id": ObjectId(folder_id),
            "is_global": True  # Only allow global folders
        })
        if not folder:
            return "Folder not found or not public", 404

        # Get owner username (assuming users collection exists)
        owner = db.users.find_one({"_id": folder["user_id"]})
        owner_username = owner.get("username", "Unknown") if owner else "Unknown"

        # Get public PDFs in this folder
        pdfs = list(pdfs_collection.find({
            "folder_id": folder_id,
            "is_global": True  # Only show global files
        }))
        
        return render_template("public_folder.html",
            folder=folder,
            pdfs=pdfs,
            owner_username=owner_username
        )
    except InvalidId:
        return "Invalid folder ID", 404

# Public file download
@app.route('/public/download/<file_id>')
def public_download(file_id):
    try:
        pdf = pdfs_collection.find_one({
            "file_id": file_id,
            "is_global": True  # Only allow global files
        })
        if not pdf:
            return "File not found or not public", 404

        file_data = fs.get(ObjectId(file_id))
        return send_file(
            file_data,
            download_name=file_data.filename,
            as_attachment=True
        )
    except InvalidId:
        return "Invalid file ID", 404
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)