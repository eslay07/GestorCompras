from gestorcompras.services import email_sender


def test_render_email_string_renders_template():
    template = "Hola {{ name }}"
    result = email_sender.render_email_string(template, {"name": "Mundo"})
    assert "Hola Mundo" == result
