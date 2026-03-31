"""
應用程式主進入點

此模組負責：
1.  初始化 Flask 應用程式。
2.  設定日誌記錄。
3.  註冊 API 藍圖。
4.  提供一個工廠函數 `create_app` 來建立和設定應用程式實例。
"""

import os
import logging
from flask import Flask, jsonify

from blueprints.credolab_routes import credolab_bp
from modules.exceptions import CredolabError


def create_app():
    app = Flask(__name__)

    # 設定日誌記錄
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # 註冊藍圖
    app.register_blueprint(credolab_bp)

    # 註冊全域錯誤處理器
    @app.errorhandler(CredolabError)
    def handle_credolab_error(error):
        """處理所有自訂的 CredolabError。"""
        response = {
            "status": "error",
            "message": str(error)
        }
        status_code = error.status_code or 500
        return jsonify(response), status_code

    @app.errorhandler(Exception)
    def handle_generic_exception(error):
        """處理所有未被捕捉的例外。"""
        logging.exception("An unhandled exception occurred.")
        response = {
            "status": "error",
            "message": "An internal server error occurred."
        }
        return jsonify(response), 500

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)