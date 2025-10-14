import psycopg2
from flask import Flask, flash, request, render_template, redirect, url_for
from config import conectar, desconectar
from datetime import datetime, date
from flask_wtf import CSRFProtect
from flask import session
import pdfkit
from flask import make_response
import base64
import mimetypes
from PIL import Image
import io
import os
from flask import send_file, abort
import smtplib
from email.message import EmailMessage
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
import requests

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
csrf = CSRFProtect(app)


def construir_mensaje_html(nombre_completo, cuerpo_principal):
    return f"""
    <p>Respetado(a) <strong>{nombre_completo}</strong>,</p>

    <p>{cuerpo_principal}</p>

    <p>Cordial saludo,<br>
    Dirección de Formación Profesional Integral<br>
    Servicio Nacional de Aprendizaje – SENA</p>

    <hr>
    <p style="font-size: 12px; color: #555;">
    <strong>**********************NO RESPONDER - Mensaje Generado Automáticamente**********************</strong><br>
    Este correo es únicamente informativo y es de uso exclusivo del destinatario(a), puede contener información privilegiada y/o confidencial. Si no es usted el destinatario(a), deberá borrarlo inmediatamente. Queda notificado que el mal uso, divulgación no autorizada, alteración y/o modificación malintencionada sobre este mensaje y sus anexos quedan estrictamente prohibidos y pueden ser legalmente sancionados. El SENA no asume ninguna responsabilidad por estas circunstancias.<br><br>
    Los servicios ofrecidos por el SENA son gratuitos y exclusivos para aprendices matriculados en programas de formación. Las opiniones contenidas en este mensaje son exclusivas de su autor y no representan la opinión del SENA o sus autoridades. El receptor deberá verificar posibles virus informáticos que tenga el correo o cualquier anexo. No se autoriza el uso de esta herramienta para el intercambio de correos masivos, cadenas o spam, ni de mensajes ofensivos, de carácter político, sexual o religioso, con fines de lucro o propósitos delictivos.
    </p>
    """
def agregar_notificacion(mensaje):
    id_actual = session.get("cuenta_actual")
    if not id_actual:
        return

    todas = session.get("notificaciones_por_usuario", {})
    notificaciones = todas.get(str(id_actual), [])
    notificaciones.append(mensaje)
    todas[str(id_actual)] = notificaciones
    session["notificaciones_por_usuario"] = todas
    session.modified = True

def notificar_usuario(destinatario, asunto, cuerpo_texto, cuerpo_html=None):
    try:
        print(f"Enviando correo a: {destinatario} con asunto: {asunto}")
        data = {
            "personalizations": [{
                "to": [{"email": destinatario}],
                "subject": asunto
            }],
            "from": {"email": "inforise.sena@gmail.com"},
            "content": [{
                "type": "text/plain",
                "value": cuerpo_texto
            }]
        }

        if cuerpo_html:
            data["content"].append({
                "type": "text/html",
                "value": cuerpo_html
            })

        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {os.getenv('SENDGRID_KEY')}",
                "Content-Type": "application/json"
            },
            json=data
        )

        if response.status_code >= 200 and response.status_code < 300:
            print("Correo enviado correctamente")
            return True
        else:
            print(f"Error al enviar correo: {response.text}")
            return False

    except Exception as e:
        print(f"Error al enviar correo: {e}")
        return False

@app.route("/Inforise/notificar_instructor/<int:id_usuario>", methods=["POST"])
def notificar_instructor(id_usuario):
    cuentas = session.get("cuentas_activas", [])
    id_actual = session.get("cuenta_actual")
    cuenta = next((c for c in cuentas if c["id"] == id_actual), None)

    if not cuenta or cuenta["tipo"] != "Coordinador":
        return "Acceso denegado", 403

    try:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, apellido, correo FROM usuarios WHERE id = %s", (id_usuario,))
        resultado = cursor.fetchone()

        if not resultado:
            flash("Error al enviar el recordatorio: el usuario no existe.", "danger")
            return redirect(url_for("instructores_pendientes"))

        nombre, apellido, correo = resultado

        if not correo:
            flash("Error al enviar el recordatorio: el usuario no tiene correo registrado.", "danger")
            return redirect(url_for("instructores_pendientes"))

        nombre_completo = f"{nombre} {apellido}"
        cuerpo_texto = "Aún no ha enviado su reporte en el sistema Inforise."
        cuerpo_principal = f"""
        Le recordamos que aún no ha enviado su reporte correspondiente en el sistema Inforise. Por favor ingrese a la plataforma y realice el envío a la mayor brevedad posible.

        Este mensaje hace parte del seguimiento académico institucional del SENA.
        """
        cuerpo_html = construir_mensaje_html(nombre_completo, cuerpo_principal)
        notificar_usuario(correo, "Recordatorio de envío de reporte – Inforise", cuerpo_texto, cuerpo_html)

        flash(f"Se ha enviado un recordatorio a {nombre_completo}.", "success")

    except Exception as e:
        flash(f"Error al enviar el recordatorio: {e}", "danger")

    finally:
        cursor.close()
        desconectar(conn)

    return redirect(url_for("instructores_pendientes"))

@app.route("/Inforise/instructores_pendientes")
def instructores_pendientes():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.nombre, u.apellido, u.correo
        FROM usuarios u
        JOIN notificaciones n ON u.id = n.id_usuario
        JOIN reportes r ON n.id_reporte = r.id
        WHERE u.tipo = 'Instructor' AND r.enviado = FALSE
    """)
    instructores = cursor.fetchall()
    cursor.close()
    desconectar(conn)
    return render_template("instructores_pendientes.html", instructores=instructores)    

@app.template_filter("b64img")
def b64img_filter(data):
    if data and isinstance(data, (bytes, bytearray)) and len(data) > 0:
        try:
            image = Image.open(io.BytesIO(data))
            mime = image.format.lower()
            if not mime or mime in ("heic", "avif", "webp"):
                image = image.convert("RGBA")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                data = buffer.getvalue()
                mime = "png"
            return f"data:image/{mime};base64,{base64.b64encode(data).decode('utf-8')}"
        except Exception as e:
            print("Error en b64img:", e)
    return ""

# Compatibilidad con plantillas antiguas
@app.template_filter("b64encode")
def b64encode_filter(data):
    import base64
    if data and isinstance(data, (bytes, bytearray)) and len(data) > 0:
        try:
            return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            print("Error en b64encode:", e)
    return ""

@app.route("/Inforise/firma/<int:usuario_id>")
def firma_usuario(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT firma FROM usuarios WHERE id = %s", (usuario_id,))
    row = cursor.fetchone()
    cursor.close()
    desconectar(conn)

    if not row or not row[0]:
        # No hay firma: devolvemos 404 para que el <img> no muestre cuadrito
        abort(404)

    data = row[0]
    try:
        # Reconvertir a PNG si fuera JPG, WebP, etc
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except Exception:
        abort(404)

@app.route("/")
def redireccion_raiz():
    return redirect(url_for("inicio_principal"))

# Ruta principal
@app.route("/Inforise")
def inicio_principal():
    return render_template("index.html")

def obtener_decisiones_ambiente():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT unnest(enum_range(NULL::decision))")
    resultados = cursor.fetchall()
    desconectar(conn)
    return [fila[0] for fila in resultados]

# Obtener tipos de ambiente (ENUM)
def obtener_tipo_ambiente():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT unnest(enum_range(NULL::tipo_ambiente))")
    resultados = cursor.fetchall()
    desconectar(conn)
    return [fila[0] for fila in resultados]

# Obtener programas existentes
def obtener_programas():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nombre, codigo, abreviatura
        FROM programas
        ORDER BY nombre
    """)
    resultados = cursor.fetchall()
    desconectar(conn)
    return resultados  # [(id, nombre, codigo, abreviatura)] ✅

# Obtener centros de formación
def obtener_centros():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nombre
        FROM centros_de_formacion
        ORDER BY nombre
    """)
    resultados = cursor.fetchall()
    desconectar(conn)
    return resultados  # [(id, nombre)]

def contar_usuarios_activos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE estado = TRUE")
    total = cursor.fetchone()[0]
    desconectar(conn)
    return total

def contar_usuarios_inactivos_sin_reportes():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM usuarios u
        WHERE u.estado = FALSE
        AND NOT EXISTS (
            SELECT 1 FROM notificaciones n WHERE n.id_usuario = u.id
        )
    """)
    total = cursor.fetchone()[0]
    desconectar(conn)
    return total

def contar_reportes_enviados():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM reportes WHERE enviado = TRUE")
    total = cursor.fetchone()[0]
    desconectar(conn)
    return total

def contar_reportes_pendientes():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) 
        FROM revisiones rev
        JOIN reportes r ON rev.id_reporte = r.id
        WHERE rev.revisado = FALSE AND r.enviado = TRUE
    """)
    total = cursor.fetchone()[0]
    desconectar(conn)
    return total

def contar_reportes_revisados():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM revisiones WHERE revisado = TRUE")
    total = cursor.fetchone()[0]
    desconectar(conn)
    return total

@app.route("/Inforise/admin/panel")
def panel_control():
    total_usuarios_activos = contar_usuarios_activos()
    total_usuarios_eliminables = contar_usuarios_inactivos_sin_reportes()
    total_reportes_enviados = contar_reportes_enviados()
    total_reportes_pendientes = contar_reportes_pendientes()
    total_reportes_revisados = contar_reportes_revisados()
    return render_template("paneldecontrol.html",
                           total_usuarios_activos=total_usuarios_activos,
                           total_usuarios_eliminables=total_usuarios_eliminables,
                           total_reportes_enviados=total_reportes_enviados,
                           total_reportes_pendientes=total_reportes_pendientes,
                           total_reportes_revisados=total_reportes_revisados)

@app.route("/Inforise/admin/gestion_usuarios", methods=["GET"])
def gestion_users():
    conexion = conectar()
    cursor = conexion.cursor()

    # Obtener usuarios con nombre + sigla del tipo de identificación
    consulta = """
        SELECT u.id, u.identificacion,
               t.nombre || ' (' || t.sigla || ')' AS tipo_identificacion,
               u.nombre, u.apellido, u.correo, u.tipo, u.estado
        FROM usuarios u
        JOIN tipo_identificacion t ON u.id_tipo_identificacion = t.id
        ORDER BY u.id
    """
    cursor.execute(consulta)
    datos = cursor.fetchall()

    cursor.close()
    desconectar(conexion)

    tipos_identificacion = obtener_tipos_identificacion()
    tipos = obtener_tipos_usuario()

    return render_template(
        "gestion_usuarios.html",
        datos=datos,
        tipos_identificacion=tipos_identificacion,
        tipos=tipos
    )

@app.route("/Inforise/admin/gestion_reportes", methods=["GET"])
def gestion_reportes():
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    orden = request.args.get("orden", "desc")
    orden_sql = "ASC" if orden == "asc" else "DESC"

    conexion = conectar()
    cursor = conexion.cursor()

    consulta = f"""
        SELECT r.id, r.regional, r.fecha,
               r.nombre_reporte,
               CONCAT(instr.nombre, ' ', instr.apellido) AS instructor,
               CONCAT(coord.nombre, ' ', coord.apellido) AS coordinador,
               rev.revisado,
               r.estado
        FROM reportes r
        JOIN notificaciones n ON n.id_reporte = r.id
        JOIN usuarios instr ON n.id_usuario = instr.id AND instr.tipo = 'Instructor'
        LEFT JOIN revisiones rev ON rev.id_reporte = r.id
        LEFT JOIN usuarios coord ON rev.id_usuario = coord.id AND coord.tipo = 'Coordinador'
    """

    datos = []
    if fecha_inicio and fecha_fin:
        consulta += " WHERE r.fecha BETWEEN %s AND %s"
        datos.extend([fecha_inicio, fecha_fin])

    consulta += f" ORDER BY r.fecha {orden_sql}"
    cursor.execute(consulta, tuple(datos))
    reportes = cursor.fetchall()

    for i in range(len(reportes)):
        reportes[i] = list(reportes[i])
        fecha = reportes[i][2]
        if isinstance(fecha, (datetime, date)):
            reportes[i][2] = fecha.strftime('%d %b %Y')
        if isinstance(reportes[i][4], str):
            reportes[i][4] = reportes[i][4].title()
        if isinstance(reportes[i][5], str):
            reportes[i][5] = reportes[i][5].title()

    cursor.close()
    desconectar(conexion)

    return render_template("gestion_reportes.html", reportes=reportes)


@app.route("/Inforise/admin/eliminar_usuario/<int:id>", methods=["POST"])
def eliminar_usuario(id):
    try:
        conexion = conectar()
        cursor = conexion.cursor()

        # Verificar si el usuario existe y está inactivo
        cursor.execute("SELECT estado FROM usuarios WHERE id = %s", (id,))
        resultado = cursor.fetchone()

        if resultado is None:
            flash("El usuario no existe.", "warning")
            return redirect(url_for("gestion_usuarios"))

        estado = resultado[0]
        if estado:  # Usuario activo
            flash("No se puede eliminar un usuario activo.", "warning")
            return redirect(url_for("gestion_usuarios"))

        # Verificar si el usuario tiene reportes asociados
        cursor.execute("SELECT COUNT(*) FROM notificaciones WHERE id_usuario = %s", (id,))
        cantidad_reportes = cursor.fetchone()[0]

        if cantidad_reportes > 0:
            flash("No se puede eliminar el usuario porque tiene reportes asociados.", "warning")
            return redirect(url_for("gestion_usuarios"))

        # Eliminar usuario inactivo sin reportes
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        conexion.commit()
        flash("El usuario fue eliminado correctamente.", "success")

    except Exception as error:
        flash("Error al eliminar el usuario.", "danger")
    finally:
        if conexion:
            cursor.close()
            desconectar(conexion)

    return redirect(url_for("gestion_usuarios"))

@app.route("/Inforise/admin/eliminar_usuarios_multiples", methods=["POST"])
def eliminar_usuarios_multiples():
    try:
        ids = request.form.getlist("usuarios")  # lista de IDs seleccionados
        conexion = conectar()
        cursor = conexion.cursor()

        eliminados = 0
        for id in ids:
            cursor.execute("SELECT estado FROM usuarios WHERE id = %s", (id,))
            estado = cursor.fetchone()
            if estado and not estado[0]:
                cursor.execute("SELECT COUNT(*) FROM notificaciones WHERE id_usuario = %s", (id,))
                reportes = cursor.fetchone()[0]
                if reportes == 0:
                    cursor.execute("DELETE FROM usuarios WHERE id = %s", (id,))
                    eliminados += 1

        conexion.commit()
        flash(f"{eliminados} usuarios fueron eliminados correctamente.", "success")

    except Exception as error:
        flash("Error al eliminar usuarios.", "danger")
    finally:
        if conexion:
            cursor.close()
            desconectar(conexion)

    return redirect(url_for("gestion_usuarios"))

@app.route("/Inforise/admin/usuario/<int:id>", methods=["POST"])
def editar_usuario(id):
    identificacion = request.form["identificacion"]
    tipo_identificacion = request.form["id_tipo_identificacion"]
    nombres = request.form["nombre"].upper()
    apellidos = request.form["apellido"].upper()
    correo = request.form["correo"]
    tipo = request.form["tipo"]
    estado = True if request.form["estado"] == "activo" else False

    try:
        conexion = conectar()
        cursor = conexion.cursor()
        consulta = """
            UPDATE usuarios SET 
            identificacion = %s, id_tipo_identificacion = %s, nombre = %s, 
            apellido = %s, correo = %s, tipo = %s, estado = %s 
            WHERE id = %s;
        """
        datos = (identificacion, tipo_identificacion, nombres, apellidos, correo, tipo, estado, id)
        cursor.execute(consulta, datos)
        conexion.commit()
        flash("El usuario fue actualizado con éxito.", "success")
    except Exception as error:
        flash("Error al actualizar el usuario.", "danger")
    finally:
        if conexion:
            cursor.close()
            desconectar(conexion)

    return redirect(url_for("gestion_users"))

@app.route("/Inforise/crear", methods=["GET", "POST"])
def crear():
    if request.method == "POST":
        regional = request.form.get("regional") or "Atlantico"
        id_programa = request.form.get("programa")
        id_centro = request.form.get("centro_de_formacion")
        localizacion = request.form.get("localizacion")
        denominacion = request.form.get("denominacion")
        tipo = request.form.get("tipo")
        codigo = request.form.get("codigo")
        nombre_reporte = request.form.get("nombre_reporte")

        cuentas = session.get("cuentas_activas", [])
        id_actual = session.get("cuenta_actual")
        cuenta = next((c for c in cuentas if c["id"] == id_actual), None)
        id_usuario = cuenta["id"] if cuenta else None

        try:
            conexion = conectar()
            cursor = conexion.cursor()

            # 1. Insertar ambiente
            cursor.execute("""
                INSERT INTO ambientes (localizacion, denominacion, tipo, estado)
                VALUES (%s, %s, %s, TRUE) RETURNING id;
            """, (localizacion, denominacion, tipo))
            id_ambiente = cursor.fetchone()[0]

            # 2. Insertar reporte
            cursor.execute("""
                INSERT INTO reportes (regional, fecha, id_programa, id_ambiente, estado, nombre_reporte, id_centroformacion)
                VALUES (%s, CURRENT_DATE, %s, %s, TRUE, %s, %s)
                RETURNING id;
            """, (regional, id_programa, id_ambiente, nombre_reporte, id_centro))
            id_reporte = cursor.fetchone()[0]

            # ✅ 3. Crear notificación para vincular al instructor
            cursor.execute("""
                INSERT INTO notificaciones (id_reporte, tipo, id_usuario, estado, fecha)
                VALUES (%s, %s, %s, TRUE, CURRENT_DATE)
            """, (id_reporte, 'Novedad', id_usuario))  # Usa un tipo válido del enum

            conexion.commit()
            agregar_notificacion(f"Reporte creado correctamente: {nombre_reporte}")
            print("Reporte y notificación creados exitosamente")
            return redirect(url_for("reportes"))

        except Exception as error:
            import traceback
            traceback.print_exc()
            print("Error al crear el reporte:", error)
            return f"Error al crear el reporte: {error}"

        finally:
            cursor.close()
            desconectar(conexion)

    programas = obtener_programas()
    centros = obtener_centros()
    tipos = obtener_tipo_ambiente()
    return render_template("crear.html", programas=programas, centros=centros, tipos=tipos)

@app.route("/Inforise/reportes", methods=["GET"])
def reportes():
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    orden = request.args.get("orden", "desc")
    orden_sql = "ASC" if orden == "asc" else "DESC"

    tipo_usuario = session.get("tipo_usuario")
    cuentas = session.get("cuentas_activas", [])
    id_actual = session.get("cuenta_actual")
    cuenta = next((c for c in cuentas if c["id"] == id_actual), None)
    id_usuario = cuenta["id"] if cuenta else None

    conexion = conectar()
    cursor = conexion.cursor()

    # 🔍 Consulta principal según tipo de usuario
    if tipo_usuario == "Instructor":
        cursor.execute(f"""
            SELECT r.id, r.regional, r.fecha, p.nombre AS programa,
                   a.localizacion, a.denominacion, a.tipo, r.nombre_reporte,
                   rev.revisado
            FROM reportes r
            JOIN programas p ON r.id_programa = p.id
            JOIN ambientes a ON r.id_ambiente = a.id
            LEFT JOIN revisiones rev ON rev.id_reporte = r.id
            WHERE r.id IN (
                SELECT id_reporte FROM notificaciones WHERE id_usuario = %s
            )
            ORDER BY r.fecha {orden_sql}
        """, (id_usuario,))
    elif tipo_usuario == "Coordinador":
        cursor.execute(f"""
            SELECT r.id, r.regional, r.fecha, p.nombre AS programa,
                   a.localizacion, a.denominacion, a.tipo, r.nombre_reporte,
                   rev.revisado
            FROM reportes r
            JOIN programas p ON r.id_programa = p.id
            JOIN ambientes a ON r.id_ambiente = a.id
            LEFT JOIN revisiones rev ON rev.id_reporte = r.id
            WHERE r.enviado = TRUE
            ORDER BY r.fecha {orden_sql}
        """)
    else:  # Admin u otros
        if fecha_inicio and fecha_fin:
            try:
                fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
                fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
                cursor.execute(f"""
                    SELECT r.id, r.regional, r.fecha, p.nombre AS programa,
                           a.localizacion, a.denominacion, a.tipo, r.nombre_reporte,
                           rev.revisado
                    FROM reportes r
                    JOIN programas p ON r.id_programa = p.id
                    JOIN ambientes a ON r.id_ambiente = a.id
                    LEFT JOIN revisiones rev ON rev.id_reporte = r.id
                    WHERE r.fecha BETWEEN %s AND %s
                    ORDER BY r.fecha {orden_sql}
                """, (fecha_inicio_dt, fecha_fin_dt))
            except ValueError:
                flash("Fechas inválidas. Mostrando todos los reportes.", "warning")
                cursor.execute(f"""
                    SELECT r.id, r.regional, r.fecha, p.nombre AS programa,
                           a.localizacion, a.denominacion, a.tipo, r.nombre_reporte,
                           rev.revisado
                    FROM reportes r
                    JOIN programas p ON r.id_programa = p.id
                    JOIN ambientes a ON r.id_ambiente = a.id
                    LEFT JOIN revisiones rev ON rev.id_reporte = r.id
                    ORDER BY r.fecha {orden_sql}
                """)
        else:
            cursor.execute(f"""
                SELECT r.id, r.regional, r.fecha, p.nombre AS programa,
                       a.localizacion, a.denominacion, a.tipo, r.nombre_reporte,
                       rev.revisado
                FROM reportes r
                JOIN programas p ON r.id_programa = p.id
                JOIN ambientes a ON r.id_ambiente = a.id
                LEFT JOIN revisiones rev ON rev.id_reporte = r.id
                ORDER BY r.fecha {orden_sql}
            """)

    reportes = cursor.fetchall()

    # ✅ Formatear la fecha como '08 Sep 2025'
    for i in range(len(reportes)):
        fecha = reportes[i][2]
        if isinstance(fecha, (datetime, date)):
            reportes[i] = list(reportes[i])
            reportes[i][2] = fecha.strftime('%d %b %Y')

    # ✅ Obtener novedades por reporte
    cursor.execute("""
        SELECT r.id AS id_reporte, n.ciudad, n.nov_ambiente, n.nov_equipos,
               n.nov_materiales, n.nov_biblioteca, n.decision_ambiente
        FROM novedades n
        JOIN notificaciones notif ON n.id_notificacion = notif.id
        JOIN reportes r ON notif.id_reporte = r.id
    """)
    novedades = cursor.fetchall()

    novedades_por_reporte = {}
    for novedad in novedades:
        id_reporte = novedad[0]
        if id_reporte not in novedades_por_reporte:
            novedades_por_reporte[id_reporte] = []
        novedades_por_reporte[id_reporte].append(novedad[1:])

    # ✅ Obtener estado de envío por reporte
    cursor.execute("SELECT id, enviado FROM reportes")
    estado_envio = cursor.fetchall()
    reporte_enviado = {r[0]: r[1] for r in estado_envio}

    # ✅ Obtener estado de revisión por reporte
    reporte_revisado = {r[0]: r[8] for r in reportes if len(r) > 8}

    cursor.close()
    desconectar(conexion)

    return render_template(
        "reportes.html",
        reportes=reportes,
        novedades_por_reporte=novedades_por_reporte,
        reporte_enviado=reporte_enviado,
        reporte_revisado=reporte_revisado
    )

@app.route("/Inforise/eliminar_reportes", methods=["POST"])
def eliminar_reportes():
    ids = request.form.getlist("reportes")
    if not ids:
        flash("No seleccionaste ningún reporte para eliminar.", "warning")
        return redirect(url_for("reportes"))

    try:
        ids = [int(i) for i in ids]  # ✅ Asegura que sean enteros
        conexion = conectar()
        cursor = conexion.cursor()

        # ✅ Verificar cuáles no han sido enviados
        cursor.execute("SELECT id FROM reportes WHERE enviado = FALSE AND id = ANY(%s)", (ids,))
        ids_permitidos = [row[0] for row in cursor.fetchall()]

        if ids_permitidos:
            # ✅ Eliminar novedades relacionadas
            cursor.execute("""
                DELETE FROM novedades
                WHERE id_notificacion IN (
                    SELECT id FROM notificaciones WHERE id_reporte = ANY(%s)
                )
            """, (ids_permitidos,))

            # ✅ Eliminar notificaciones relacionadas
            cursor.execute("DELETE FROM notificaciones WHERE id_reporte = ANY(%s)", (ids_permitidos,))

            # ✅ Eliminar reportes
            cursor.execute("DELETE FROM reportes WHERE id = ANY(%s)", (ids_permitidos,))
            conexion.commit()
            flash(f"{len(ids_permitidos)} reporte(s) eliminado(s) con éxito.", "success")
            agregar_notificacion(f"Se eliminaron {len(ids_permitidos)} reporte(s).")
        else:
            flash("Solo se pueden eliminar reportes no enviados.", "danger")

    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"Ocurrió un error al eliminar los reportes: {e}", "danger")
    finally:
        cursor.close()
        desconectar(conexion)

    return redirect(url_for("reportes"))

@app.route("/Inforise/nombrar/<int:id_reporte>", methods=["POST"])
def nombrar_reporte(id_reporte):
    nombre_manual = request.form.get("nombre")

    try:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT regional, fecha FROM reportes WHERE id = %s", (id_reporte,))
        resultado = cursor.fetchone()

        if not resultado:
            return "Reporte no encontrado", 404

        regional, fecha = resultado
        fecha_str = fecha.strftime("%Y%m%d")
        nombre_final = nombre_manual.strip() if nombre_manual else f"Reporte_{regional}_{fecha_str}_{id_reporte}"

        cursor.execute("UPDATE reportes SET nombre_reporte = %s WHERE id = %s", (nombre_final, id_reporte))
        conn.commit()
        agregar_notificacion(f"Nombre asignado al reporte #{id_reporte}.")
        print(f"Nombre asignado al reporte #{id_reporte}: {nombre_final}")
    except Exception as e:
        print("Error al nombrar el reporte:", e)
        return f"Error al nombrar el reporte: {e}", 500
    finally:
        cursor.close()
        desconectar(conn)

    return redirect("/Inforise/reportes")

@app.route("/Inforise/reporte/<int:id_reporte>/novedad", methods=["POST"])
def agregar_novedad(id_reporte):
    ciudad = request.form.get("ciudad")
    nov_ambiente = request.form.get("nov_ambiente")
    nov_equipos = request.form.get("nov_equipos")
    nov_materiales = request.form.get("nov_materiales")
    nov_biblioteca = request.form.get("nov_biblioteca")
    decision_ambiente = request.form.get("decision_ambiente")

    try:
        conexion = conectar()
        cursor = conexion.cursor()

        # 1. Buscar el id_notificacion asociado a este reporte
        cursor.execute("SELECT id FROM notificaciones WHERE id_reporte = %s LIMIT 1", (id_reporte,))
        resultado = cursor.fetchone()
        if not resultado:
            # Si no existe, la creamos con tipo 'NOVEDAD'
            cursor.execute("INSERT INTO notificaciones (id_reporte, tipo) VALUES (%s, %s) RETURNING id;", (id_reporte, 'Novedad'))
            id_notificacion = cursor.fetchone()[0]
        else:
            id_notificacion = resultado[0]

        # 2. Insertar la novedad con el id_notificacion
        consulta = """
            INSERT INTO novedades (ciudad, nov_ambiente, nov_equipos, nov_materiales, nov_biblioteca, decision_ambiente, estado, fecha, id_notificacion)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, CURRENT_DATE, %s)
        """
        datos = (ciudad, nov_ambiente, nov_equipos, nov_materiales, nov_biblioteca, decision_ambiente, id_notificacion)
        cursor.execute(consulta, datos)
        conexion.commit()
        print("Novedad agregada exitosamente")

    except (Exception, psycopg2.Error) as error:
        print("Error al agregar la novedad:", error)
        return f"Error al agregar la novedad: {error}", 500

    finally:
        cursor.close()
        desconectar(conexion)

    return redirect(url_for("reportes"))


@app.route("/Inforise/reporte/<int:id_reporte>", methods=["GET"])
def ver_reporte(id_reporte):
    conn = conectar()
    cursor = conn.cursor()

    # Verificar si el reporte fue enviado
    cursor.execute("SELECT enviado FROM reportes WHERE id = %s", (id_reporte,))
    estado = cursor.fetchone()
    if estado and estado[0]:  # Si fue enviado
        cursor.close()
        desconectar(conn)
        flash("Este reporte ya fue enviado y no se puede agregar novedad.", "warning")
        return redirect(url_for("reportes"))

    # Obtener datos del reporte (incluyendo código del programa)
    cursor.execute("""
    SELECT r.id, r.regional, r.fecha,
           p.nombre AS programa, p.codigo AS codigo,
           a.localizacion, a.denominacion, a.tipo,
           c.nombre AS centro_formacion
    FROM reportes r
    LEFT JOIN programas p ON r.id_programa = p.id
    LEFT JOIN ambientes a ON r.id_ambiente = a.id
    LEFT JOIN centros_de_formacion c ON r.id_centroformacion = c.id
    WHERE r.id = %s;
    """, (id_reporte,))
    reporte = cursor.fetchone()

    # Obtener datos para formulario de novedades
    decisiones = obtener_decisiones_ambiente()

    cursor.close()
    desconectar(conn)

    return render_template(
        "detalle_reporte.html",
        reporte=reporte,
        decisiones=decisiones
    )

@app.route("/Inforise/editar/<int:id_reporte>", methods=["GET", "POST"])
def editar_reporte(id_reporte):
    if request.method == "POST":
        id_ambiente = request.form.get("id_ambiente")
        id_novedad = request.form.get("id_novedad")

        regional = request.form.get("regional")
        id_centro = request.form.get("centro_de_formacion")
        id_programa = request.form.get("programa")
        codigo = request.form.get("codigo")
        localizacion = request.form.get("localizacion")
        denominacion = request.form.get("denominacion")
        tipo = request.form.get("tipo")

        ciudad = request.form.get("ciudad")
        nov_ambiente = request.form.get("nov_ambiente")
        nov_equipos = request.form.get("nov_equipos")
        nov_materiales = request.form.get("nov_materiales")
        nov_biblioteca = request.form.get("nov_biblioteca")
        decision_ambiente = request.form.get("decision_ambiente")

        try:
            conexion = conectar()
            cursor = conexion.cursor()

            # Verificar si el reporte fue enviado
            cursor.execute("SELECT enviado FROM reportes WHERE id = %s", (id_reporte,))
            estado = cursor.fetchone()
            if estado and estado[0]:
                cursor.close()
                desconectar(conexion)
                flash("Este reporte ya fue enviado y no puede editarse.", "warning")
                return redirect(url_for("reportes"))

            # Actualizar ambiente
            cursor.execute("""
                UPDATE ambientes
                SET localizacion = %s, denominacion = %s, tipo = %s
                WHERE id = %s;
            """, (localizacion, denominacion, tipo, id_ambiente))

            # Actualizar reporte
            cursor.execute("""
                UPDATE reportes
                SET regional = %s, fecha = CURRENT_DATE, id_programa = %s, id_ambiente = %s, id_centroformacion = %s
                WHERE id = %s;
            """, (regional, id_programa, id_ambiente, id_centro, id_reporte))

            # Actualizar novedad
            cursor.execute("""
                UPDATE novedades
                SET ciudad = %s, nov_ambiente = %s, nov_equipos = %s, nov_materiales = %s, nov_biblioteca = %s, decision_ambiente = %s, fecha = CURRENT_DATE
                WHERE id = %s;
            """, (ciudad, nov_ambiente, nov_equipos, nov_materiales, nov_biblioteca, decision_ambiente, id_novedad))

            conexion.commit()
            print("Reporte actualizado exitosamente")
            agregar_notificacion(f"Reporte #{id_reporte} actualizado correctamente.")
            return redirect(f"/Inforise/reporte/{id_reporte}")
        except Exception as error:
            import traceback
            traceback.print_exc()
            return f"Error al actualizar el reporte: {error}"
        finally:
            if conexion:
                cursor.close()
                desconectar(conexion)
    else:
        conn = conectar()
        cursor = conn.cursor()

        # Verificar si el reporte fue enviado
        cursor.execute("SELECT enviado FROM reportes WHERE id = %s", (id_reporte,))
        estado = cursor.fetchone()
        if estado and estado[0]:
            cursor.close()
            desconectar(conn)
            flash("Este reporte ya fue enviado y no puede editarse.", "warning")
            return redirect(url_for("reportes"))

        cursor.execute("""
            SELECT r.id, r.regional, r.fecha, r.id_programa, r.id_ambiente, r.id_centroformacion,
                   a.localizacion, a.denominacion, a.tipo,
                   n.id, n.ciudad, n.nov_ambiente, n.nov_equipos, n.nov_materiales, n.nov_biblioteca, n.decision_ambiente
            FROM reportes r
            LEFT JOIN ambientes a ON r.id_ambiente = a.id
            LEFT JOIN notificaciones notif ON notif.id_reporte = r.id
            LEFT JOIN novedades n ON n.id_notificacion = notif.id
            WHERE r.id = %s
            LIMIT 1
        """, (id_reporte,))
        row = cursor.fetchone()

        if not row:
            cursor.close()
            desconectar(conn)
            return "Reporte no encontrado", 404

        reporte = {
            "id": row[0],
            "regional": row[1],
            "fecha": row[2],
            "id_programa": row[3],
            "id_ambiente": row[4],
            "id_centroformacion": row[5],
            "localizacion": row[6],
            "denominacion": row[7],
            "tipo": row[8]
        }
        novedad = {
            "id": row[9],
            "ciudad": row[10],
            "nov_ambiente": row[11],
            "nov_equipos": row[12],
            "nov_materiales": row[13],
            "nov_biblioteca": row[14],
            "decision_ambiente": row[15]
        }

        programas = obtener_programas()
        centros = obtener_centros()
        tipos = obtener_tipo_ambiente()
        decisiones = obtener_decisiones_ambiente()

        cursor.close()
        desconectar(conn)

        return render_template(
            "editar.html",
            reporte=reporte,
            novedad=novedad,
            programas=programas,
            centros=centros,
            tipos=tipos,
            decisiones=decisiones
        )
    
@app.route("/Inforise/enviar/<int:id_reporte>", methods=["POST"])
def enviar_reporte(id_reporte):
    cuentas = session.get("cuentas_activas", [])
    id_actual = session.get("cuenta_actual")
    cuenta = next((c for c in cuentas if c["id"] == id_actual), None)

    if not cuenta or cuenta["tipo"] != "Instructor":
        return "Acceso denegado", 403

    id_usuario = cuenta["id"]

    try:
        conn = conectar()
        cursor = conn.cursor()

        # ✅ Validar que el instructor está vinculado al reporte
        cursor.execute("""
            SELECT id FROM notificaciones
            WHERE id_reporte = %s AND id_usuario = %s
        """, (id_reporte, id_usuario))
        if not cursor.fetchone():
            return "No tienes permiso para enviar este reporte", 403

        cursor.execute("UPDATE reportes SET enviado = TRUE WHERE id = %s", (id_reporte,))

        # Insertar revisión pendiente
        cursor.execute("""
        INSERT INTO revisiones (id_reporte, revisado)
        VALUES (%s, FALSE)
        """, (id_reporte,))

        conn.commit()
        # Datos del instructor
        cursor.execute("SELECT nombre, apellido, correo FROM usuarios WHERE id = %s", (id_usuario,))
        nombre, apellido, correo_instructor = cursor.fetchone()

        # Datos del coordinador
        cursor.execute("SELECT correo FROM usuarios WHERE tipo = 'Coordinador' LIMIT 1")
        correo_coord = cursor.fetchone()[0]

        # Notificación al instructor
        nombre_completo = f"{nombre} {apellido}"
        cuerpo_texto = f"Su reporte #{id_reporte} ha sido enviado correctamente."
        cuerpo_principal = f"""
        Le informamos que su reporte <strong>#{id_reporte}</strong> ha sido enviado correctamente a través del sistema Inforise. Este será revisado por el coordinador correspondiente.

        Gracias por cumplir con sus responsabilidades académicas como instructor del SENA.
        """
        cuerpo_html = construir_mensaje_html(nombre_completo, cuerpo_principal)
        notificar_usuario(correo_instructor, "Confirmación de envío de reporte – Inforise", cuerpo_texto, cuerpo_html)

        # Notificación al coordinador
        nombre_completo = "Coordinador(a)"
        cuerpo_texto = f"Ha recibido un nuevo reporte del instructor {nombre} {apellido}."
        cuerpo_principal = f"""
        El instructor <strong>{nombre} {apellido}</strong> ha enviado el reporte <strong>#{id_reporte}</strong> correspondiente a su programa de formación. Puede acceder al sistema Inforise para realizar la revisión correspondiente.

        Gracias por su gestión y seguimiento académico.
        """
        cuerpo_html = construir_mensaje_html(nombre_completo, cuerpo_principal)
        notificar_usuario(correo_coord, "Nuevo reporte recibido – Inforise", cuerpo_texto, cuerpo_html)

    except Exception as e:
        return f"Error al enviar el reporte: {e}", 500
    finally:
        cursor.close()
        desconectar(conn)
        flash("Reporte enviado y notificación enviada al coordinador.", "success")
        agregar_notificacion(f"Reporte #{id_reporte} enviado correctamente.")
    return redirect(url_for("reportes"))
    
@app.route("/Inforise/revisiones", methods=["GET"])
def revisiones():
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    orden = request.args.get("orden", "desc")
    orden_sql = "ASC" if orden == "asc" else "DESC"

    conexion = conectar()
    cursor = conexion.cursor()

    # 🔍 Consulta principal con nombre y apellido del instructor
    consulta_base = f"""
    SELECT r.id, r.regional, r.fecha,
           p.nombre AS programa,
           a.localizacion, a.denominacion, a.tipo,
           r.nombre_reporte,
           CONCAT(u.nombre, ' ', u.apellido) AS instructor,
           rev.revisado
    FROM reportes r
    JOIN programas p ON r.id_programa = p.id
    JOIN ambientes a ON r.id_ambiente = a.id
    JOIN notificaciones n ON n.id_reporte = r.id
    JOIN usuarios u ON n.id_usuario = u.id
    LEFT JOIN revisiones rev ON rev.id_reporte = r.id
"""

    datos = []
    if fecha_inicio and fecha_fin:
        consulta_base += " WHERE r.enviado = TRUE AND r.fecha BETWEEN %s AND %s"
        datos.extend([fecha_inicio, fecha_fin])
    else:
        consulta_base += " WHERE r.enviado = TRUE"

    consulta_base += f" ORDER BY r.fecha {orden_sql}"
    cursor.execute(consulta_base, tuple(datos))
    reportes = cursor.fetchall()

    # ✅ Formatear fecha como '21 Sep 2025'
    for i in range(len(reportes)):
        fecha = reportes[i][2]
        if isinstance(fecha, (datetime, date)):
            reportes[i] = list(reportes[i])
            reportes[i][2] = fecha.strftime('%d %b %Y')

    # ✅ Formatear nombre del instructor
    nombre_instructor = reportes[i][8]
    if isinstance(nombre_instructor, str):
        reportes[i][8] = nombre_instructor.title()        

    # ✅ Obtener novedades por reporte
    cursor.execute("""
        SELECT r.id AS id_reporte, n.ciudad, n.nov_ambiente, n.nov_equipos,
               n.nov_materiales, n.nov_biblioteca, n.decision_ambiente
        FROM novedades n
        JOIN notificaciones notif ON n.id_notificacion = notif.id
        JOIN reportes r ON notif.id_reporte = r.id
    """)
    novedades = cursor.fetchall()

    cursor.close()
    desconectar(conexion)

    # ✅ Agrupar novedades por reporte
    novedades_por_reporte = {}
    for novedad in novedades:
        id_reporte = novedad[0]
        if id_reporte not in novedades_por_reporte:
            novedades_por_reporte[id_reporte] = []
        novedades_por_reporte[id_reporte].append(novedad[1:])

    return render_template(
        "revisiones.html",
        reportes=reportes,
        novedades_por_reporte=novedades_por_reporte
    )

@app.route("/Inforise/revisar/<int:id_reporte>", methods=["POST"])
def marcar_revisado(id_reporte):
    conexion = conectar()
    cursor = conexion.cursor()

    # Verifica si ya existe una revisión para este reporte
    cursor.execute("SELECT id FROM revisiones WHERE id_reporte = %s", (id_reporte,))
    existe = cursor.fetchone()

    if existe:
        # Si existe, actualiza el campo revisado
        cursor.execute("""
            UPDATE revisiones SET revisado = TRUE WHERE id_reporte = %s
        """, (id_reporte,))
    else:
        # Si no existe, inserta una nueva revisión marcada como revisada
        cursor.execute("""
            INSERT INTO revisiones (id_reporte, revisado) VALUES (%s, TRUE)
        """, (id_reporte,))

        conexion.commit()
        # Datos del instructor
        cursor.execute("""
        SELECT u.nombre, u.apellido, u.correo
        FROM notificaciones n
        JOIN usuarios u ON n.id_usuario = u.id
        WHERE n.id_reporte = %s
        """, (id_reporte,))
        nombre, apellido, correo_instructor = cursor.fetchone()

        # Datos del coordinador
        id_coord = session.get("id_usuario")
        cursor.execute("SELECT nombre, correo FROM usuarios WHERE id = %s", (id_coord,))
        nombre_coord, correo_coord = cursor.fetchone()

        # Notificación al instructor
        nombre_completo = f"{nombre} {apellido}"
        cuerpo_texto = f"Su reporte #{id_reporte} ha sido revisado por el coordinador."
        cuerpo_principal = f"""
        Le informamos que su reporte <strong>#{id_reporte}</strong> ha sido revisado por el coordinador asignado.

        Gracias por su compromiso con el proceso académico institucional.
        """
        cuerpo_html = construir_mensaje_html(nombre_completo, cuerpo_principal)
        notificar_usuario(correo_instructor, "Su reporte ha sido revisado – Inforise", cuerpo_texto, cuerpo_html)

        # Notificación al coordinador
        nombre_completo = f"{nombre_coord}"
        cuerpo_texto = f"Ha marcado el reporte #{id_reporte} como revisado."
        cuerpo_principal = f"""
        Se ha registrado correctamente la revisión del reporte <strong>#{id_reporte}</strong> en el sistema Inforise.

        Gracias por su gestión académica como coordinador del SENA.
        """
        cuerpo_html = construir_mensaje_html(nombre_completo, cuerpo_principal)
        notificar_usuario(correo_coord, "Revisión completada – Inforise", cuerpo_texto, cuerpo_html)

    cursor.close()
    desconectar(conexion)

    return redirect(url_for("revisiones"))

@app.route("/Inforise/revision/<int:id_reporte>", methods=["GET"])
def ver_revision(id_reporte):
    conn = conectar()
    cursor = conn.cursor()

    # Verificar si el reporte ya fue revisado
    cursor.execute("SELECT revisado FROM revisiones WHERE id_reporte = %s", (id_reporte,))
    estado = cursor.fetchone()
    if estado and estado[0]:  # Si ya fue revisado
        cursor.close()
        desconectar(conn)
        flash("Este reporte ya fue revisado y no puede abrirse nuevamente.", "warning")
        return redirect(url_for("revisiones"))

    # Obtener datos del reporte
    cursor.execute("""
        SELECT r.id, r.regional, r.fecha,
               p.nombre AS programa, p.codigo AS codigo,
               a.localizacion, a.denominacion, a.tipo,
               c.nombre AS centro_formacion,
               r.id_programa, r.id_centroformacion
        FROM reportes r
        LEFT JOIN programas p ON r.id_programa = p.id
        LEFT JOIN ambientes a ON r.id_ambiente = a.id
        LEFT JOIN centros_de_formacion c ON r.id_centroformacion = c.id
        WHERE r.id = %s;
    """, (id_reporte,))
    reporte_raw = cursor.fetchone()

    campos_reporte = [
        'id', 'regional', 'fecha', 'programa', 'codigo_programa',
        'localizacion', 'denominacion', 'tipo', 'centro_formacion',
        'id_programa', 'id_centroformacion'
    ]
    reporte = dict(zip(campos_reporte, reporte_raw)) if reporte_raw else None

    # Obtener la novedad asociada al reporte
    cursor.execute("""
        SELECT n.ciudad, n.nov_ambiente, n.nov_equipos, n.nov_materiales,
               n.nov_biblioteca, n.decision_ambiente
        FROM novedades n
        JOIN notificaciones notif ON n.id_notificacion = notif.id
        WHERE notif.id_reporte = %s
        LIMIT 1;
    """, (id_reporte,))
    novedad_raw = cursor.fetchone()

    campos_novedad = ['ciudad', 'nov_ambiente', 'nov_equipos', 'nov_materiales', 'nov_biblioteca', 'decision_ambiente']
    novedad = dict(zip(campos_novedad, novedad_raw)) if novedad_raw else None

    decisiones = obtener_decisiones_ambiente()

    cursor.close()
    desconectar(conn)

    return render_template(
        "detalle_revision.html",
        reporte=reporte,
        decisiones=decisiones,
        novedad=novedad
    )

@app.route("/Inforise/revision/guardar/<int:id_reporte>", methods=["POST"])
def guardar_revision(id_reporte):
    ciudad = request.form.get("ciudad")
    id_usuario = session.get("id_usuario")  # Coordinador logueado

    conn = conectar()
    cursor = conn.cursor()

    # Insertar la revisión en la tabla correspondiente
    cursor.execute("""
        INSERT INTO revisiones (id_reporte, id_usuario, ciudad, fecha_revision, estado)
        VALUES (%s, %s, %s, CURRENT_DATE, TRUE)
    """, (id_reporte, id_usuario, ciudad))

    conn.commit()
    agregar_notificacion(f"Revisión registrada para el reporte #{id_reporte}.")
    cursor.close()
    desconectar(conn)

    return redirect(url_for("revisiones"))

def obtener_datos_reporte(id_reporte):
    conn = conectar()
    cursor = conn.cursor()

    # 1. Datos del reporte (incluye nombre_reporte)
    cursor.execute("""
        SELECT r.id, r.regional, r.fecha, r.nombre_reporte,
               p.nombre AS programa, p.codigo AS codigo,
               a.localizacion, a.denominacion, a.tipo,
               c.nombre AS centro_formacion
        FROM reportes r
        LEFT JOIN programas p ON r.id_programa = p.id
        LEFT JOIN ambientes a ON r.id_ambiente = a.id
        LEFT JOIN centros_de_formacion c ON r.id_centroformacion = c.id
        WHERE r.id = %s;
    """, (id_reporte,))
    reporte_raw = cursor.fetchone()

    campos_reporte = [
        'id', 'regional', 'fecha', 'nombre_reporte',
        'programa', 'codigo_programa',
        'localizacion', 'denominacion', 'tipo', 'centro_formacion'
    ]
    reporte = dict(zip(campos_reporte, reporte_raw)) if reporte_raw else None

    # 2. Novedad
    cursor.execute("""
        SELECT n.ciudad, n.fecha, n.nov_ambiente, n.nov_equipos, n.nov_materiales,
               n.nov_biblioteca, n.decision_ambiente, notif.id_usuario
        FROM novedades n
        JOIN notificaciones notif ON n.id_notificacion = notif.id
        WHERE notif.id_reporte = %s
        LIMIT 1;
    """, (id_reporte,))
    novedad_raw = cursor.fetchone()

    campos_novedad = [
        'ciudad', 'fecha', 'nov_ambiente', 'nov_equipos',
        'nov_materiales', 'nov_biblioteca', 'decision_ambiente', 'id_usuario_instructor'
    ]
    novedad = dict(zip(campos_novedad, novedad_raw)) if novedad_raw else {}

    # 3. Revisión
    cursor.execute("""
        SELECT ciudad, fecha_revision, id_usuario
        FROM revisiones
        WHERE id_reporte = %s
        LIMIT 1;
    """, (id_reporte,))
    revision_raw = cursor.fetchone()

    revision = {
        'ciudad': revision_raw[0],
        'fecha_revision': revision_raw[1],
        'id_usuario': revision_raw[2]
    } if revision_raw else None

    # 4. Instructor
    if novedad.get('id_usuario_instructor'):
        cursor.execute("""
            SELECT nombre, apellido, firma
            FROM usuarios
            WHERE id = %s AND tipo = 'Instructor';
        """, (novedad['id_usuario_instructor'],))
        instructor_raw = cursor.fetchone()

        if instructor_raw:
            novedad['nombre_instructor'] = instructor_raw[0]
            novedad['apellido_instructor'] = instructor_raw[1]
            novedad['firma_instructor'] = bytes(instructor_raw[2]) if instructor_raw[2] else b''

    # 5. Coordinador
    if revision and revision.get('id_usuario'):
        cursor.execute("""
            SELECT nombre, apellido, firma
            FROM usuarios
            WHERE id = %s AND tipo = 'Coordinador';
        """, (revision['id_usuario'],))
        coordinador_raw = cursor.fetchone()

        if coordinador_raw:
            novedad['nombre_coordinador'] = coordinador_raw[0]
            novedad['apellido_coordinador'] = coordinador_raw[1]
            novedad['firma_coordinador'] = bytes(coordinador_raw[2]) if coordinador_raw[2] else b''
            novedad['ciudad_revision'] = revision['ciudad']
            novedad['fecha_revision'] = revision['fecha_revision']

    cursor.close()
    desconectar(conn)
    return reporte, novedad


# ---------------------------
# Rutas
# ---------------------------
@app.route("/Inforise/reporte/<int:id_reporte>")
def descargar(id_reporte):
    reporte, novedad = obtener_datos_reporte(id_reporte)
    return render_template("descargar.html", reporte=reporte, novedad=novedad)


@app.route("/Inforise/pdf/<int:id_reporte>")
def generar_pdf(id_reporte):
    reporte, novedad = obtener_datos_reporte(id_reporte)

    # Fecha de creación
    if 'fecha' in novedad and novedad['fecha']:
        novedad['fecha_formateada'] = novedad['fecha'].strftime('%d/%m/%Y')
    else:
        novedad['fecha_formateada'] = 'Sin fecha'

    # Fecha de revisión
    if 'fecha_revision' in novedad and novedad['fecha_revision']:
        novedad['fecha_revision_formateada'] = novedad['fecha_revision'].strftime('%d/%m/%Y')
    else:
        novedad['fecha_revision_formateada'] = None

    if os.name == 'nt':
        config = pdfkit.configuration(wkhtmltopdf=r"C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe")
    else:
        config = None

    logo_path = os.path.join(app.root_path, 'static', 'logosena.png')
    rendered_html = render_template("descargar.html", reporte=reporte, novedad=novedad, logo_path=logo_path)

    options = {
        'enable-local-file-access': None
    }

    css_path = os.path.join(app.root_path, 'static', 'estilos', 'descargar.css')

    try:
        pdf = pdfkit.from_string(rendered_html, False, configuration=config, options=options, css=css_path)
    except Exception as e:
        print("Error al generar PDF:", e)
        return "Error interno al generar el PDF", 500

    nombre_archivo = reporte['nombre_reporte'].strip().replace(" ", "_").replace("/", "-")

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}.pdf'
    return response

@app.route("/Inforise/registrarse", methods=["GET", "POST"])
def registrarse():
    if request.method == "POST":
        nombre = request.form["nombre"]
        apellido = request.form["apellido"]
        identificacion = request.form["identificacion"]
        correo = request.form["correo"]
        tipo = request.form["tipo"]  # Ej: "Coordinador", "Instructor", "Admin"
        contrasena_plana = request.form["contrasena"]
        contrasena = generate_password_hash(contrasena_plana)
        id_tipo_identificacion = int(request.form["id_tipo_identificacion"].strip())
      
        firma_file = request.files.get("firma")
        firma_bytes = firma_file.read() if firma_file and firma_file.filename else None

        try:
            conexion = conectar()
            cursor = conexion.cursor()
            consulta = """
                INSERT INTO usuarios (
                    nombre, apellido, identificacion, correo,
                    firma, tipo, contrasena, id_tipo_identificacion
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            datos = (
                nombre, apellido, identificacion, correo,
                firma_bytes, tipo, contrasena, id_tipo_identificacion
            )
            cursor.execute(consulta, datos)
            conexion.commit()
            flash("✅ Usuario registrado con éxito", "success")
            nombre_completo = f"{nombre} {apellido}"
            cuerpo_texto = f"Su cuenta como {tipo} ha sido creada exitosamente en el sistema Inforise del SENA."
            cuerpo_principal = f"""
            El Servicio Nacional de Aprendizaje SENA le informa que su cuenta en el sistema <strong>Inforise</strong> ha sido activada exitosamente como <strong>{tipo}</strong>. Esta plataforma está destinada exclusivamente para instructores y coordinadores vinculados a procesos académicos de formación profesional.

            Agradecemos su compromiso con la gestión educativa institucional.
            """
            cuerpo_html = construir_mensaje_html(nombre_completo, cuerpo_principal)
            notificar_usuario(correo, "Bienvenido(a) a Inforise – SENA", cuerpo_texto, cuerpo_html)
        except (Exception, psycopg2.Error) as error:
            print("Error al registrar al Usuario:", error)
            flash("❌ Error al registrar al usuario", "danger")
        finally:
            if conexion:
                cursor.close()
                desconectar(conexion)

        # Recarga la vista con datos para evitar errores
        tipos = obtener_tipos_usuario()
        tipos_identificacion = obtener_tipos_identificacion()
        return render_template("registrarse.html", tipos=tipos, tipos_identificacion=tipos_identificacion)

    else:
        tipos = obtener_tipos_usuario()
        tipos_identificacion = obtener_tipos_identificacion()
        return render_template("registrarse.html", tipos=tipos, tipos_identificacion=tipos_identificacion)
  
# Función para obtener los tipos de usuario desde PostgreSQL
def obtener_tipos_usuario():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT unnest(enum_range(NULL::tipo_usuario))")
    resultados = cursor.fetchall()
    desconectar(conn)
    return [fila[0] for fila in resultados]

# Función para obtener tipos de identificación desde PostgreSQL
def obtener_tipos_identificacion():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, sigla FROM tipo_identificacion ORDER BY nombre")
    resultados = cursor.fetchall()
    desconectar(conn)
    return [{"id": fila[0], "nombre": fila[1], "sigla": fila[2]} for fila in resultados]

@app.route("/Inforise/login", methods=['GET', 'POST'])
def login():
    error = None
    tipos_identificacion = obtener_tipos_identificacion()

    if request.method == 'POST':
        id_tipo_identificacion = request.form.get('id_tipo_identificacion')
        identificacion = request.form.get('identificacion')
        contrasena = request.form.get('contrasena')

        if not id_tipo_identificacion or not identificacion or not contrasena:
            error = 'Todos los campos son obligatorios'
        else:
            try:
                id_tipo_identificacion = int(id_tipo_identificacion)

                conn = conectar()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, nombre, tipo, correo, contrasena
                    FROM usuarios
                    WHERE id_tipo_identificacion = %s AND identificacion = %s
                """, (id_tipo_identificacion, identificacion))
                resultado = cursor.fetchone()
                cursor.close()
                desconectar(conn)

                if resultado is None:
                    error = 'Usuario no encontrado'
                else:
                    if check_password_hash(resultado[4], contrasena):
                        nueva_cuenta = {
                            "id": resultado[0],
                            "nombre": resultado[1],
                            "tipo": resultado[2],
                            "correo": resultado[3]
                        }

                        # Inicializa lista de cuentas activas si no existe
                        if "cuentas_activas" not in session:
                            session["cuentas_activas"] = []

                        # Evita duplicados
                        if not any(c["id"] == nueva_cuenta["id"] for c in session["cuentas_activas"]):
                            session["cuentas_activas"].append(nueva_cuenta)

                        # Establece la cuenta actual
                        session["cuenta_actual"] = nueva_cuenta["id"]
                        session["tipo_usuario"] = nueva_cuenta["tipo"]       
                        session["id_usuario"] = nueva_cuenta["id"]
                        session["notificaciones"] = []  # 🔥 Esto inicializa la lista
                        session.modified = True            

                        # Redirige según tipo
                        tipo_usuario = nueva_cuenta["tipo"]
                        if tipo_usuario == "Coordinador":
                            return redirect(url_for("vista_coordinador"))
                        elif tipo_usuario == "Instructor":
                            return redirect(url_for("vista_instructor"))
                        elif tipo_usuario == "Admin":
                            return redirect(url_for("vista_admin"))
                        else:
                            error = f"Tipo de usuario no reconocido: {tipo_usuario}"
                    else:
                        error = 'Credenciales inválidas'
            except ValueError:
                error = 'Tipo de identificación inválido'

    return render_template("login.html", tipos_identificacion=tipos_identificacion, error=error)


@app.route("/Inforise/recuperar-contrasena", methods=['GET', 'POST'])
def recuperar_contrasena():
    error = None
    mensaje = None
    tipos_identificacion = obtener_tipos_identificacion()

    if request.method == 'POST':
        id_tipo_identificacion = request.form.get('id_tipo_identificacion')
        identificacion = request.form.get('identificacion')
        correo = request.form.get('correo')
        nueva_contrasena_plana = request.form.get('nueva_contrasena')

        if not id_tipo_identificacion or not identificacion or not correo or not nueva_contrasena_plana:
            error = "Todos los campos son obligatorios"
        else:
            try:
                id_tipo_identificacion = int(id_tipo_identificacion)
                conn = conectar()
                cursor = conn.cursor()

                # Buscar usuario con todos los datos necesarios
                cursor.execute("""
                    SELECT id, nombre, apellido, tipo FROM usuarios
                    WHERE id_tipo_identificacion = %s AND identificacion = %s AND correo = %s
                """, (id_tipo_identificacion, identificacion, correo))
                resultado = cursor.fetchone()

                if resultado:
                    id_usuario, nombre, apellido, tipo = resultado

                    # Cifrar la nueva contraseña
                    nueva_contrasena_cifrada = generate_password_hash(nueva_contrasena_plana.strip())

                    # Actualizar contraseña cifrada
                    cursor.execute("""
                        UPDATE usuarios SET contrasena = %s WHERE id = %s
                    """, (nueva_contrasena_cifrada, id_usuario))
                    conn.commit()

                    if session.get("cuenta_actual"):
                        agregar_notificacion("Tu contraseña fue actualizada correctamente.")

                    # Enviar correo institucional
                    nombre_completo = f"{nombre} {apellido}"
                    cuerpo_texto = "Su contraseña ha sido actualizada correctamente en el sistema Inforise del SENA."
                    cuerpo_principal = f"""
                    Le informamos que su contraseña ha sido modificada exitosamente en el sistema <strong>Inforise</strong> del SENA. Esta acción fue realizada desde su cuenta registrada como <strong>{tipo}</strong>.

                    Por razones de seguridad, le recomendamos no compartir sus credenciales y mantenerlas actualizadas periódicamente.

                    Si usted no realizó esta acción, por favor comuníquese de inmediato con el equipo de soporte institucional.
                    """
                    cuerpo_html = construir_mensaje_html(nombre_completo, cuerpo_principal)
                    notificar_usuario(correo, "Confirmación de cambio de contraseña – Inforise", cuerpo_texto, cuerpo_html)

                    mensaje = "Contraseña actualizada correctamente"
                else:
                    error = "Usuario no encontrado con esos datos"

                cursor.close()
                desconectar(conn)

            except Exception as e:
                print("Error al procesar la solicitud:", e)
                error = "Error al procesar la solicitud"

    return render_template("recuperar_contrasena.html", tipos_identificacion=tipos_identificacion, error=error, mensaje=mensaje)

@app.route("/Inforise/cambiar_cuenta", methods=["POST"])
def cambiar_cuenta():
    id_cuenta = int(request.form.get("id_cuenta"))
    session["cuenta_actual"] = id_cuenta
    return redirect(url_for("inicio_principal"))

@app.route("/Inforise/eliminar_cuenta", methods=["POST"])
def quitar_cuenta():
    id_cuenta = int(request.form.get("id_cuenta"))

    session["cuentas_activas"] = [
        cuenta for cuenta in session["cuentas_activas"]
        if cuenta["id"] != id_cuenta
    ]

    if session.get("cuenta_actual") == id_cuenta:
        if session["cuentas_activas"]:
            session["cuenta_actual"] = session["cuentas_activas"][0]["id"]
        else:
            session.clear()

    return redirect(url_for("inicio_principal"))

@app.route("/Inforise/coordinador")
def vista_coordinador():
    return render_template("inicio_coordinador.html")

@app.route("/Inforise/instructor")
def vista_instructor():
    return render_template("inicio_instructor.html")

@app.route("/Inforise/admin")
def vista_admin():
    return render_template("inicio_admin.html")

@app.route("/Inforise/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/Inforise/configuracion", methods=["GET", "POST"])
def configuracion():
    cuentas   = session.get("cuentas_activas", [])
    id_actual = session.get("cuenta_actual")
    cuenta    = next((c for c in cuentas if c["id"] == id_actual), None)
    if not cuenta:
        return redirect(url_for("login"))
    id_usuario = cuenta["id"]

    conn   = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        nombre                 = request.form.get("nombre")
        apellido               = request.form.get("apellido")
        identificacion         = request.form.get("identificacion")
        correo                 = request.form.get("correo")
        tipo                   = request.form.get("tipo")
        id_tipo_identificacion = int(request.form.get("id_tipo_identificacion").strip())

        firma_file  = request.files.get("firma")
        firma_bytes = None
        if firma_file and firma_file.filename:
            raw = firma_file.read()
            try:
                img = Image.open(io.BytesIO(raw)).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                firma_bytes = buf.getvalue()
            except Exception as e:
                app.logger.error(f"Error convirtiendo firma: {e}")
                firma_bytes = raw

        if firma_bytes:
            cursor.execute("""
                UPDATE usuarios
                SET nombre                 = %s,
                    apellido               = %s,
                    id_tipo_identificacion = %s,
                    identificacion         = %s,
                    correo                 = %s,
                    tipo                   = %s,
                    firma                  = %s
                WHERE id = %s
            """, (
                nombre, apellido,
                id_tipo_identificacion,
                identificacion, correo,
                tipo, firma_bytes,
                id_usuario
            ))
            flash("Firma guardada correctamente. Si deseas reemplazarla, sube una nueva imagen.", "success")
        else:
            cursor.execute("""
                UPDATE usuarios
                SET nombre                 = %s,
                    apellido               = %s,
                    id_tipo_identificacion = %s,
                    identificacion         = %s,
                    correo                 = %s,
                    tipo                   = %s
                WHERE id = %s
            """, (
                nombre, apellido,
                id_tipo_identificacion,
                identificacion, correo,
                tipo, id_usuario
            ))
            flash("Datos guardados correctamente.", "success")

        conn.commit()

    cursor.execute("""
        SELECT nombre, apellido,
               id_tipo_identificacion,
               identificacion, correo,
               tipo, firma
        FROM usuarios
        WHERE id = %s
    """, (id_usuario,))
    usuario = cursor.fetchone()

    cursor.close()
    desconectar(conn)

    return render_template(
        "configuracion.html",
        usuario=usuario,
        id_usuario=id_usuario,
        tipos=obtener_tipos_usuario(),
        tipos_identificacion=obtener_tipos_identificacion()
    )


if __name__ == '__main__':
    app.run(debug=True)



