
import os
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
from config import get_db_connection
from s3_config import s3_client, S3_BUCKET
from werkzeug.utils import secure_filename
import uuid

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")


@app.route("/")
def home():

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM products ORDER BY id DESC")
            products = cursor.fetchall()

        for product in products:
            image_key = product.get("image_url")

            if image_key:
                try:
                    product["image_presigned_url"] = (
                        s3_client.generate_presigned_url(
                            "get_object",
                            Params={
                                "Bucket": S3_BUCKET,
                                "Key": image_key
                            },
                            ExpiresIn=3600
                        )
                    )
                except Exception as error:
                    print("S3 image URL error:", error)
                    product["image_presigned_url"] = None
            else:
                product["image_presigned_url"] = None

        return render_template("index.html", products=products)

    finally:
        connection.close()

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM admin_users WHERE username = %s",
                    (username,)
                )
                admin = cursor.fetchone()

        finally:
            connection.close()

        if admin and check_password_hash(
            admin["password_hash"], password
        ):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]

            return redirect(url_for("admin_dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM products ORDER BY id DESC")
            products = cursor.fetchall()

        return render_template(
            "admin_dashboard.html",
            products=products
        )

    finally:
        connection.close()
@app.route("/admin/add-product", methods=["GET", "POST"])
def add_product():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()

        image = request.files.get("image")
        image_key = None

        try:
            price = float(request.form.get("price", 0))
            stock = int(request.form.get("stock", 0))

            if not name or price <= 0 or stock < 0:
                raise ValueError("Invalid product details.")

            if image and image.filename:

                filename = secure_filename(image.filename)
                extension = filename.rsplit(".", 1)[-1].lower()

                allowed_extensions = {"jpg", "jpeg", "png", "webp"}

                if extension not in allowed_extensions:
                    raise ValueError("Only JPG, PNG and WEBP images are allowed.")

                image.stream.seek(0, 2)
                file_size = image.stream.tell()
                image.stream.seek(0)

                if file_size > 5 * 1024 * 1024:
                    raise ValueError("Image size must not exceed 5 MB.")

                content_types = {
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "png": "image/png",
                    "webp": "image/webp"
                }

                image_key = f"products/{uuid.uuid4().hex}_{filename}"

                s3_client.upload_fileobj(
                    image,
                    S3_BUCKET,
                    image_key,
                    ExtraArgs={
                        "ContentType": content_types[extension],
                        "ServerSideEncryption": "AES256"
                    }
                )

            connection = get_db_connection()

            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO products
                        (name, description, price, category, stock, image_url)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (name, description, price, category, stock, image_key)
                    )

                connection.commit()

            finally:
                connection.close()

            flash("Product added successfully!", "success")
            return redirect(url_for("admin_dashboard"))

        except (ValueError, TypeError) as error:
            flash(str(error), "danger")

    return render_template("add_product.html")


@app.route("/admin/edit-product/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    connection = get_db_connection()
    new_image_key = None

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                "SELECT * FROM products WHERE id = %s",
                (product_id,)
            )
            product = cursor.fetchone()

            if not product:
                flash("Product not found.", "danger")
                return redirect(url_for("admin_dashboard"))

            if request.method == "POST":

                name = request.form.get("name", "").strip()
                description = request.form.get("description", "").strip()
                category = request.form.get("category", "").strip()

                try:
                    price = float(request.form.get("price", 0))
                    stock = int(request.form.get("stock", 0))

                    if not name or price <= 0 or stock < 0:
                        raise ValueError()

                except (ValueError, TypeError):
                    flash("Please enter valid product details.", "danger")
                    return render_template(
                        "edit_product.html", product=product
                    )

                image = request.files.get("image")
                old_image_key = product.get("image_url")
                image_key = old_image_key

                try:
                    # Upload a replacement image only if selected
                    if image and image.filename:

                        filename = secure_filename(image.filename)
                        extension = filename.rsplit(".", 1)[-1].lower()

                        allowed_extensions = {
                            "jpg", "jpeg", "png", "webp"
                        }

                        if extension not in allowed_extensions:
                            raise ValueError(
                                "Only JPG, PNG and WEBP images are allowed."
                            )

                        image.stream.seek(0, 2)
                        file_size = image.stream.tell()
                        image.stream.seek(0)

                        if file_size > 5 * 1024 * 1024:
                            raise ValueError(
                                "Image size must not exceed 5 MB."
                            )

                        content_types = {
                            "jpg": "image/jpeg",
                            "jpeg": "image/jpeg",
                            "png": "image/png",
                            "webp": "image/webp"
                        }

                        new_image_key = (
                            f"products/{uuid.uuid4().hex}_{filename}"
                        )

                        s3_client.upload_fileobj(
                            image,
                            S3_BUCKET,
                            new_image_key,
                            ExtraArgs={
                                "ContentType": content_types[extension],
                                "ServerSideEncryption": "AES256"
                            }
                        )

                        image_key = new_image_key

                    cursor.execute(
                        """
                        UPDATE products
                        SET name=%s, description=%s, category=%s,
                            price=%s, stock=%s, image_url=%s
                        WHERE id=%s
                        """,
                        (
                            name, description, category,
                            price, stock, image_key, product_id
                        )
                    )

                    connection.commit()

                except Exception as error:

                    connection.rollback()

                    # Remove newly uploaded image if DB update failed
                    if new_image_key:
                        try:
                            s3_client.delete_object(
                                Bucket=S3_BUCKET,
                                Key=new_image_key
                            )
                        except Exception as cleanup_error:
                            print("S3 cleanup error:", cleanup_error)

                    flash(str(error), "danger")
                    return render_template(
                        "edit_product.html", product=product
                    )

                # Delete old image only after successful DB update
                if new_image_key and old_image_key:
                    try:
                        s3_client.delete_object(
                            Bucket=S3_BUCKET,
                            Key=old_image_key
                        )
                    except Exception as error:
                        print("Old S3 image cleanup error:", error)

                flash("Product updated successfully!", "success")
                return redirect(url_for("admin_dashboard"))

        return render_template("edit_product.html", product=product)

    finally:
        connection.close()


@app.route("/admin/delete-product/<int:product_id>", methods=["POST"])
def delete_product(product_id):

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    connection = get_db_connection()
    image_key = None

    try:
        with connection.cursor() as cursor:

            # Retrieve the product and its S3 image key
            cursor.execute(
                "SELECT image_url FROM products WHERE id = %s",
                (product_id,)
            )
            product = cursor.fetchone()

            if not product:
                flash("Product not found.", "danger")
                return redirect(url_for("admin_dashboard"))

            image_key = product.get("image_url")

            # Delete the product from MySQL
            cursor.execute(
                "DELETE FROM products WHERE id = %s",
                (product_id,)
            )

        connection.commit()

        # Delete the associated image from S3
        if image_key:
            try:
                s3_client.delete_object(
                    Bucket=S3_BUCKET,
                    Key=image_key
                )
                flash(
                    "Product and its S3 image deleted successfully!",
                    "success"
                )

            except Exception as error:
                print("S3 image deletion error:", error)
                flash(
                    "Product deleted, but its S3 image could not be deleted.",
                    "warning"
                )
        else:
            flash("Product deleted successfully!", "success")

    finally:
        connection.close()

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():

    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/test-db")
def test_db():

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()

        return {
            "status": "success",
            "message": "MySQL connected successfully",
            "tables": tables
        }

    finally:
        connection.close()


if __name__ == "__main__":
    app.run(debug=True)
