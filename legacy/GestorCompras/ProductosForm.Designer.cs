using System;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    partial class ProductosForm
    {
        private System.ComponentModel.IContainer components = null;
        private System.Windows.Forms.TextBox txtCodigoBuscar;
        private System.Windows.Forms.TextBox txtCodigo;
        private System.Windows.Forms.TextBox txtNombre;
        private System.Windows.Forms.TextBox txtCategoria;
        private System.Windows.Forms.TextBox txtPrecio;
        private System.Windows.Forms.Button btnBuscar;
        private System.Windows.Forms.Button btnModificar;
        private System.Windows.Forms.Button btnAgregar;
        private System.Windows.Forms.Button btnRegresar;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            this.Text = "Gestión de Productos";
            this.Size = new System.Drawing.Size(400, 300);
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;

            Label lblCodigoBuscar = new Label() { Text = "Código:", Left = 10, Top = 10, Width = 80 };
            txtCodigoBuscar = new TextBox() { Left = 100, Top = 10, Width = 150 };
            btnBuscar = new Button() { Text = "Buscar", Left = 260, Top = 10, Width = 100 };
            btnBuscar.Click += new EventHandler(btnBuscar_Click);

            Label lblCodigo = new Label() { Text = "Código:", Left = 10, Top = 50, Width = 80 };
            txtCodigo = new TextBox() { Left = 100, Top = 50, Width = 260 };
            Label lblNombre = new Label() { Text = "Nombre:", Left = 10, Top = 80, Width = 80 };
            txtNombre = new TextBox() { Left = 100, Top = 80, Width = 260 };
            Label lblCategoria = new Label() { Text = "Categoría:", Left = 10, Top = 110, Width = 80 };
            txtCategoria = new TextBox() { Left = 100, Top = 110, Width = 260 };
            Label lblPrecio = new Label() { Text = "Precio:", Left = 10, Top = 140, Width = 80 };
            txtPrecio = new TextBox() { Left = 100, Top = 140, Width = 260 };

            btnModificar = new Button() { Text = "Modificar", Left = 10, Top = 180, Width = 170 };
            btnModificar.Click += new EventHandler(btnModificar_Click);

            btnAgregar = new Button() { Text = "Agregar", Left = 190, Top = 180, Width = 170 };
            btnAgregar.Click += new EventHandler(btnAgregar_Click);

            btnRegresar = new Button() { Text = "Regresar", Left = 100, Top = 230, Width = 170 };
            btnRegresar.Click += new EventHandler(btnRegresar_Click);

            // Agregar todos los controles al formulario, incluyendo los labels
            this.Controls.Add(lblCodigoBuscar);
            this.Controls.Add(txtCodigoBuscar);
            this.Controls.Add(btnBuscar);
            this.Controls.Add(lblCodigo);
            this.Controls.Add(txtCodigo);
            this.Controls.Add(lblNombre);
            this.Controls.Add(txtNombre);
            this.Controls.Add(lblCategoria);
            this.Controls.Add(txtCategoria);
            this.Controls.Add(lblPrecio);
            this.Controls.Add(txtPrecio);
            this.Controls.Add(btnModificar);
            this.Controls.Add(btnAgregar);
            this.Controls.Add(btnRegresar);
        }
    }
}
