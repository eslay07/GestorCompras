import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from gestorcompras.utils import test_email_connection
from gestorcompras.logic import despacho_logic


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

    @app.route('/', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            if not user or not password:
                flash('Debe ingresar usuario y contraseña.', 'danger')
            else:
                email = f"{user}@telconet.ec"
                if test_email_connection(email, password):
                    session['email'] = email
                    session['password'] = password
                    flash('Inicio de sesión correcto.', 'success')
                    return redirect(url_for('menu'))
                flash('Usuario o contraseña incorrectos.', 'danger')
        return render_template('login.html')

    @app.route('/menu')
    def menu():
        if 'email' not in session:
            return redirect(url_for('login'))
        return render_template('menu.html')

    def _ensure_login():
        if 'email' not in session:
            return redirect(url_for('login'))
        return None

    @app.route('/reasignacion')
    def reasignacion():
        if (r := _ensure_login()) is not None:
            return r
        return render_template('placeholder.html', title='Reasignación de Tareas')

    @app.route('/despacho', methods=['GET', 'POST'])
    def despacho():
        if (r := _ensure_login()) is not None:
            return r
        result = None
        if request.method == 'POST':
            orden = request.form.get('orden', '').strip()
            include_pdf = bool(request.form.get('include_pdf'))
            template = request.form.get('template') or None
            email_session = {'address': session['email'], 'password': session['password']}
            result = despacho_logic.process_order(email_session, orden, include_pdf, template)
        return render_template('despacho.html', result=result)

    @app.route('/seguimientos')
    def seguimientos():
        if (r := _ensure_login()) is not None:
            return r
        return render_template('placeholder.html', title='Seguimientos')

    @app.route('/descargas_oc')
    def descargas_oc():
        if (r := _ensure_login()) is not None:
            return r
        return render_template('placeholder.html', title='Descargas OC')

    @app.route('/cotizador')
    def cotizador():
        if (r := _ensure_login()) is not None:
            return r
        return render_template('placeholder.html', title='Cotizador')

    @app.route('/configuracion')
    def configuracion():
        if (r := _ensure_login()) is not None:
            return r
        return render_template('placeholder.html', title='Configuración')

    @app.route('/logout')
    def logout():
        session.clear()
        flash('Sesión cerrada.', 'info')
        return redirect(url_for('login'))

    return app
