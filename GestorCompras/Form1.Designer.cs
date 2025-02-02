namespace ProyectoCotizador
{
    partial class Form1
    {
        private System.ComponentModel.IContainer components = null;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code
        private void InitializeComponent()
        {
            this.btnProveedores = new System.Windows.Forms.Button();
            this.btnCotizador = new System.Windows.Forms.Button();
            this.btnTareas = new System.Windows.Forms.Button();
            this.btnSalir = new System.Windows.Forms.Button();
            this.label1 = new System.Windows.Forms.Label();
            this.SuspendLayout();
            // 
            // btnProveedores
            // 
            this.btnProveedores.BackColor = System.Drawing.Color.SteelBlue;
            this.btnProveedores.Font = new System.Drawing.Font("Arial", 12F, System.Drawing.FontStyle.Bold);
            this.btnProveedores.ForeColor = System.Drawing.Color.White;
            this.btnProveedores.Location = new System.Drawing.Point(99, 145);
            this.btnProveedores.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnProveedores.Name = "btnProveedores";
            this.btnProveedores.Size = new System.Drawing.Size(225, 75);
            this.btnProveedores.TabIndex = 0;
            this.btnProveedores.Text = "Proveedores";
            this.btnProveedores.UseVisualStyleBackColor = false;
            this.btnProveedores.Click += new System.EventHandler(this.btnProveedores_Click);
            // 
            // btnCotizador
            // 
            this.btnCotizador.BackColor = System.Drawing.Color.SteelBlue;
            this.btnCotizador.Font = new System.Drawing.Font("Arial", 12F, System.Drawing.FontStyle.Bold);
            this.btnCotizador.ForeColor = System.Drawing.Color.White;
            this.btnCotizador.Location = new System.Drawing.Point(99, 228);
            this.btnCotizador.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnCotizador.Name = "btnCotizador";
            this.btnCotizador.Size = new System.Drawing.Size(225, 75);
            this.btnCotizador.TabIndex = 1;
            this.btnCotizador.Text = "Cotizador";
            this.btnCotizador.UseVisualStyleBackColor = false;
            this.btnCotizador.Click += new System.EventHandler(this.btnCotizador_Click);
            // 
            // btnTareas
            // 
            this.btnTareas.BackColor = System.Drawing.Color.SteelBlue;
            this.btnTareas.Font = new System.Drawing.Font("Arial", 12F, System.Drawing.FontStyle.Bold);
            this.btnTareas.ForeColor = System.Drawing.Color.White;
            this.btnTareas.Location = new System.Drawing.Point(99, 311);
            this.btnTareas.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnTareas.Name = "btnTareas";
            this.btnTareas.Size = new System.Drawing.Size(225, 75);
            this.btnTareas.TabIndex = 2;
            this.btnTareas.Text = "Tareas";
            this.btnTareas.UseVisualStyleBackColor = false;
            this.btnTareas.Click += new System.EventHandler(this.btnTareas_Click);
            // 
            // btnSalir
            // 
            this.btnSalir.BackColor = System.Drawing.Color.Firebrick;
            this.btnSalir.Font = new System.Drawing.Font("Arial", 12F, System.Drawing.FontStyle.Bold);
            this.btnSalir.ForeColor = System.Drawing.Color.White;
            this.btnSalir.Location = new System.Drawing.Point(99, 431);
            this.btnSalir.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnSalir.Name = "btnSalir";
            this.btnSalir.Size = new System.Drawing.Size(225, 75);
            this.btnSalir.TabIndex = 3;
            this.btnSalir.Text = "Salir";
            this.btnSalir.UseVisualStyleBackColor = false;
            this.btnSalir.Click += new System.EventHandler(this.btnSalir_Click);
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.BackColor = System.Drawing.SystemColors.Window;
            this.label1.ForeColor = System.Drawing.Color.DarkTurquoise;
            this.label1.Location = new System.Drawing.Point(136, 67);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(148, 20);
            this.label1.TabIndex = 4;
            this.label1.Text = "Gestor de Compras";
            this.label1.Click += new System.EventHandler(this.label1_Click);
            // 
            // Form1
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(9F, 20F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.WhiteSmoke;
            this.ClientSize = new System.Drawing.Size(430, 625);
            this.Controls.Add(this.label1);
            this.Controls.Add(this.btnProveedores);
            this.Controls.Add(this.btnCotizador);
            this.Controls.Add(this.btnTareas);
            this.Controls.Add(this.btnSalir);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedSingle;
            this.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.MaximizeBox = false;
            this.Name = "Form1";
            this.Text = "Menú Principal";
            this.ResumeLayout(false);
            this.PerformLayout();

        }
        #endregion

        private System.Windows.Forms.Button btnProveedores;
        private System.Windows.Forms.Button btnCotizador;
        private System.Windows.Forms.Button btnTareas;
        private System.Windows.Forms.Button btnSalir;
        private System.Windows.Forms.Label label1;
    }
}