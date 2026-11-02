from app import create_app

app = create_app({"DEVELOPMENT": True}) if __name__ == "__main__" else create_app()

if __name__ == "__main__":
    app.run(debug=True)
