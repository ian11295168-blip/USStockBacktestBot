
"""US Stock Strategy Lab v1.9 — 登入與雲端檢視入口。

啟動：
    python -m streamlit run secure_app.py

登入後：
- 策略分析平台（原 web_app.py）
- Supabase 雲端資料（cloud_view.py）

尚未完成正式雲端身分驗證，
不可直接部署為公開網站。
"""

import hashlib
import hmac

import streamlit as st


st.set_page_config(
    page_title="US Stock Strategy Lab",
    page_icon="🔐",
    layout="wide",
)


def get_login_config():
    try:
        return st.secrets["local_login"]
    except (KeyError, FileNotFoundError):
        return None


def verify_password(password, config):
    try:
        salt = bytes.fromhex(
            config["salt"]
        )

        expected = bytes.fromhex(
            config["password_hash"]
        )

        iterations = int(
            config["iterations"]
        )

        if (
            len(salt) != 32
            or len(expected) != 32
            or iterations < 600_000
        ):
            return False

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )

        return hmac.compare_digest(
            actual, expected
        )

    except (
        KeyError,
        ValueError,
        TypeError,
        OverflowError,
    ):
        return False


def login_page():
    st.title("🔐 US Stock Strategy Lab")
    st.subheader("登入股票策略分析系統")

    st.write(
        "登入後可以使用策略回測、"
        "Telegram 紀錄與 Supabase 雲端檢視。"
    )

    config = get_login_config()

    if config is None:
        st.error(
            "登入設定不存在。"
            "請先執行 python setup_login.py"
        )
        st.stop()

    with st.form("login_form"):
        password = st.text_input(
            "登入密碼",
            type="password",
        )

        submit = st.form_submit_button(
            "🔓 登入",
            type="primary",
            use_container_width=True,
        )

    if submit:
        if verify_password(password, config):
            st.session_state[
                "_lab_authenticated"
            ] = True

            st.session_state[
                "_lab_login_failures"
            ] = 0

            st.rerun()

        else:
            st.session_state[
                "_lab_login_failures"
            ] = (
                st.session_state.get(
                    "_lab_login_failures", 0
                ) + 1
            )

            st.error("密碼錯誤，請重新輸入。")

    st.caption(
        "本機單人登入測試版。"
        "尚未完成正式雲端身分驗證。"
    )


def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.rerun()


def cloud_page():
    """只在登入後執行雲端檢視。"""

    from cloud_view import main

    main()


if st.session_state.get(
    "_lab_authenticated", False
):
    # 登入後才註冊受保護頁面
    home = st.Page(
        "web_app.py",
        title="策略分析平台",
        icon="📈",
        default=True,
    )

    cloud = st.Page(
        cloud_page,
        title="雲端資料",
        icon="☁️",
        url_path="cloud",
    )

    page = st.navigation(
        [home, cloud],
        position="hidden",
    )

    with st.sidebar:
        st.caption("🔐 已登入")

        st.page_link(
            home,
            label="📈 策略分析平台",
            use_container_width=True,
        )

        st.page_link(
            cloud,
            label="☁️ 雲端資料",
            use_container_width=True,
        )

        if st.button(
            "🔒 登出帳號",
            use_container_width=True,
        ):
            logout()

        st.divider()

    page.run()

else:
    # 未登入時，不註冊任何資料頁面
    page = st.navigation(
        [
            st.Page(
                login_page,
                title="登入",
                default=True,
            )
        ],
        position="hidden",
    )

    page.run()
