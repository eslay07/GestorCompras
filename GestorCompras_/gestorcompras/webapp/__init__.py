import os
import subprocess
import sys
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash
from gestorcompras.utils import test_email_connection
from gestorcompras.logic import despacho_logic
from gestorcompras.services import db, google_sheets
from gestorcompras.webapp import reasignacion


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

    @app.route('/reasignacion', methods=['GET', 'POST'])
    def reasignacion():
        if (r := _ensure_login()) is not None:
            return r
        msg = None
        if request.method == 'POST':
            if 'load' in request.form:
                date = request.form.get('date') or ''
                count, msg = reasignacion.load_tasks_from_email(
                    session['email'], session['password'], date
                )
            elif 'process' in request.form:
                task_id = int(request.form.get('task_id'))
                task = next((t for t in db.get_tasks_temp() if t['id'] == task_id), None)
                if task:
                    msg = reasignacion.process_task_web(
                        session['email'], session['password'], task
                    )
                    db.delete_task_temp(task_id)
        tasks = db.get_tasks_temp()
        return render_template('reasignacion.html', tasks=tasks, message=msg)

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

    @app.route('/seguimientos', methods=['GET', 'POST'])
    def seguimientos():
        if (r := _ensure_login()) is not None:
            return r
        msg = None
        creds = db.get_config("GOOGLE_CREDS", "")
        sid = db.get_config("GOOGLE_SHEET_ID", "")
        sname = db.get_config("GOOGLE_SHEET_NAME", "")
        orders = []
        if creds and sid and sname:
            try:
                orders = google_sheets.read_report(creds, sid, sname)
            except Exception as e:
                msg = str(e)
        else:
            msg = "Debe configurar Google Sheets."
        templates = [tpl[1] for tpl in db.get_email_templates()]
        if request.method == 'POST':
            selected = request.form.getlist('orders')
            template = request.form.get('template') or None
            attach = bool(request.form.get('attach_pdf'))
            email_session = {'address': session['email'], 'password': session['password']}
            logs = []
            for oc in selected:
                res = despacho_logic.process_order(
                    email_session, oc, include_pdf=attach,
                    template_name=template, cc_key='EMAIL_CC_SEGUIMIENTO'
                )
                logs.append(res)
            msg = "\n".join(logs) if logs else "No se seleccionaron órdenes"
        return render_template('seguimientos.html', orders=orders, templates=templates, message=msg)

    @app.route('/descargas_oc', methods=['GET', 'POST'])
    def descargas_oc():
        if (r := _ensure_login()) is not None:
            return r
        msg = None
        if request.method == 'POST':
            script = Path(__file__).resolve().parents[2] / 'DescargasOC-main' / 'descargas_oc' / 'ui.py'
            subprocess.Popen([sys.executable, str(script)])
            msg = 'Proceso iniciado en segundo plano.'
        return render_template('descargas.html', message=msg)

    @app.route('/cotizador')
    def cotizador():
        if (r := _ensure_login()) is not None:
            return r
        return render_template('placeholder.html', title='Cotizador')

    @app.route('/configuracion', methods=['GET', 'POST'])
    def configuracion():
        if (r := _ensure_login()) is not None:
            return r
        msg = None
        if request.method == 'POST':
            if 'add_supplier' in request.form:
                name = request.form.get('name')
                ruc = request.form.get('ruc')
                email_sup = request.form.get('email')
                email_alt = request.form.get('email_alt') or None
                if name and ruc and email_sup:
                    db.add_supplier(name, ruc, email_sup, email_alt)
                    msg = 'Proveedor agregado'
            elif 'add_assignment' in request.form:
                sub = request.form.get('subdept')
                dept = request.form.get('dept')
                person = request.form.get('person')
                if sub and dept and person:
                    db.set_assignment_config(sub, dept, person)
                    msg = 'Asignación guardada'
        suppliers = db.get_suppliers()
        assignments = db.get_assignments()
        return render_template('configuracion.html', suppliers=suppliers, assignments=assignments, message=msg)

    @app.route('/logout')
    def logout():
        session.clear()
        flash('Sesión cerrada.', 'info')
        return redirect(url_for('login'))

    return app
