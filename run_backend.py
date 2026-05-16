# #!/usr/bin/env python3
# """
# Run the backend server.
# """
# import sys
# import os

# # Add the project root to Python path
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# from backend.api.app import create_app

# if __name__ == '__main__':
#     app = create_app()
#     port = int(os.environ.get("PORT", 5009))
#     app.run(host="0.0.0.0", port=port, debug=False)
#     # app.run(host='0.0.0.0', port=5009, debug=True)