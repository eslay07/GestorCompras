namespace ProyectoCotizador
{
    partial class CotizadorForm
    {
        private System.ComponentModel.IContainer components = null;

        private System.Windows.Forms.Panel panelTop;
        private System.Windows.Forms.Label lblNumeroTarea;
        private System.Windows.Forms.TextBox txtNumeroTarea;
        private System.Windows.Forms.Label lblCategoria;
        private System.Windows.Forms.ComboBox cmbCategoria;
        private System.Windows.Forms.DataGridView dgvProductos;
        private System.Windows.Forms.Panel panelBottom;
        private System.Windows.Forms.Button btnPegarExcel;
        private System.Windows.Forms.Button btnCotKatuk;
        private System.Windows.Forms.Button btnRegresar;
        private System.Windows.Forms.Button btnCotcorreo_Click;
        private System.Windows.Forms.DataGridViewTextBoxColumn dataGridViewTextBoxColumn1;
        private System.Windows.Forms.DataGridViewTextBoxColumn dataGridViewTextBoxColumn2;

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
            this.panelTop = new System.Windows.Forms.Panel();
            this.lblCategoria = new System.Windows.Forms.Label();
            this.cmbCategoria = new System.Windows.Forms.ComboBox();
            this.lblNumeroTarea = new System.Windows.Forms.Label();
            this.txtNumeroTarea = new System.Windows.Forms.TextBox();
            this.dgvProductos = new System.Windows.Forms.DataGridView();
            this.DESCRIPCION = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.CANTIDAD = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.panelBottom = new System.Windows.Forms.Panel();
            this.btnCotcorreo_Click = new System.Windows.Forms.Button();
            this.btnRegresar = new System.Windows.Forms.Button();
            this.btnCotKatuk = new System.Windows.Forms.Button();
            this.btnPegarExcel = new System.Windows.Forms.Button();
            this.BtnGuardar_Click = new System.Windows.Forms.Button();
            this.panelTop.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dgvProductos)).BeginInit();
            this.panelBottom.SuspendLayout();
            this.SuspendLayout();
            // 
            // panelTop
            // 
            this.panelTop.Controls.Add(this.lblCategoria);
            this.panelTop.Controls.Add(this.cmbCategoria);
            this.panelTop.Controls.Add(this.lblNumeroTarea);
            this.panelTop.Controls.Add(this.txtNumeroTarea);
            this.panelTop.Dock = System.Windows.Forms.DockStyle.Top;
            this.panelTop.Location = new System.Drawing.Point(0, 0);
            this.panelTop.Name = "panelTop";
            this.panelTop.Size = new System.Drawing.Size(1176, 139);
            this.panelTop.TabIndex = 0;
            // 
            // lblCategoria
            // 
            this.lblCategoria.AutoSize = true;
            this.lblCategoria.Location = new System.Drawing.Point(18, 54);
            this.lblCategoria.Name = "lblCategoria";
            this.lblCategoria.Size = new System.Drawing.Size(82, 20);
            this.lblCategoria.TabIndex = 3;
            this.lblCategoria.Text = "Categoría:";
            // 
            // cmbCategoria
            // 
            this.cmbCategoria.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.cmbCategoria.FormattingEnabled = true;
            this.cmbCategoria.Location = new System.Drawing.Point(110, 49);
            this.cmbCategoria.Name = "cmbCategoria";
            this.cmbCategoria.Size = new System.Drawing.Size(298, 28);
            this.cmbCategoria.TabIndex = 2;
            // 
            // lblNumeroTarea
            // 
            this.lblNumeroTarea.AutoSize = true;
            this.lblNumeroTarea.Location = new System.Drawing.Point(18, 14);
            this.lblNumeroTarea.Name = "lblNumeroTarea";
            this.lblNumeroTarea.Size = new System.Drawing.Size(136, 20);
            this.lblNumeroTarea.TabIndex = 1;
            this.lblNumeroTarea.Text = "Número de Tarea:";
            // 
            // txtNumeroTarea
            // 
            this.txtNumeroTarea.Location = new System.Drawing.Point(174, 9);
            this.txtNumeroTarea.Name = "txtNumeroTarea";
            this.txtNumeroTarea.Size = new System.Drawing.Size(234, 26);
            this.txtNumeroTarea.TabIndex = 0;
            // 
            // dgvProductos
            // 
            this.dgvProductos.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvProductos.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.DESCRIPCION,
            this.CANTIDAD});
            this.dgvProductos.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dgvProductos.Location = new System.Drawing.Point(0, 139);
            this.dgvProductos.Name = "dgvProductos";
            this.dgvProductos.RowHeadersWidth = 62;
            this.dgvProductos.Size = new System.Drawing.Size(1176, 447);
            this.dgvProductos.TabIndex = 1;
            this.dgvProductos.CellContentClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dgvProductos_CellContentClick_1);
            // 
            // DESCRIPCION
            // 
            this.DESCRIPCION.MinimumWidth = 8;
            this.DESCRIPCION.Name = "DESCRIPCION";
            this.DESCRIPCION.Width = 150;
            // 
            // CANTIDAD
            // 
            this.CANTIDAD.MinimumWidth = 8;
            this.CANTIDAD.Name = "CANTIDAD";
            this.CANTIDAD.Width = 150;
            // 
            // panelBottom
            // 
            this.panelBottom.Controls.Add(this.BtnGuardar_Click);
            this.panelBottom.Controls.Add(this.btnCotcorreo_Click);
            this.panelBottom.Controls.Add(this.btnRegresar);
            this.panelBottom.Controls.Add(this.btnCotKatuk);
            this.panelBottom.Controls.Add(this.btnPegarExcel);
            this.panelBottom.Dock = System.Windows.Forms.DockStyle.Bottom;
            this.panelBottom.Location = new System.Drawing.Point(0, 586);
            this.panelBottom.Name = "panelBottom";
            this.panelBottom.Size = new System.Drawing.Size(1176, 92);
            this.panelBottom.TabIndex = 2;
            // 
            // btnCotcorreo_Click
            // 
            this.btnCotcorreo_Click.Location = new System.Drawing.Point(333, 23);
            this.btnCotcorreo_Click.Name = "btnCotcorreo_Click";
            this.btnCotcorreo_Click.Size = new System.Drawing.Size(141, 46);
            this.btnCotcorreo_Click.TabIndex = 3;
            this.btnCotcorreo_Click.Text = "Cot. Correo";
            this.btnCotcorreo_Click.UseVisualStyleBackColor = true;
            this.btnCotcorreo_Click.Click += new System.EventHandler(this.btnCotcorreo);
            // 
            // btnRegresar
            // 
            this.btnRegresar.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnRegresar.Location = new System.Drawing.Point(996, 23);
            this.btnRegresar.Name = "btnRegresar";
            this.btnRegresar.Size = new System.Drawing.Size(150, 46);
            this.btnRegresar.TabIndex = 2;
            this.btnRegresar.Text = "Regresar";
            this.btnRegresar.UseVisualStyleBackColor = true;
            this.btnRegresar.Click += new System.EventHandler(this.btnRegresar_Click);
            // 
            // btnCotKatuk
            // 
            this.btnCotKatuk.Location = new System.Drawing.Point(480, 23);
            this.btnCotKatuk.Name = "btnCotKatuk";
            this.btnCotKatuk.Size = new System.Drawing.Size(150, 46);
            this.btnCotKatuk.TabIndex = 1;
            this.btnCotKatuk.Text = "Cotizar Katuk";
            this.btnCotKatuk.UseVisualStyleBackColor = true;
            this.btnCotKatuk.Click += new System.EventHandler(this.btnCotKatuk_Click);
            // 
            // btnPegarExcel
            // 
           // this.btnPegarExcel.Location = new System.Drawing.Point(18, 23);
            //this.btnPegarExcel.Name = "btnPegarExcel";
            //this.btnPegarExcel.Size = new System.Drawing.Size(150, 46);
            //this.btnPegarExcel.TabIndex = 0;
            //this.btnPegarExcel.Text = "Pegar Excel";
            //this.btnPegarExcel.UseVisualStyleBackColor = true;
            //this.btnPegarExcel.Click += new System.EventHandler(this.btnPegarExcel_Click);
            // 
            // BtnGuardar_Click
            // 
            this.BtnGuardar_Click.Location = new System.Drawing.Point(194, 23);
            this.BtnGuardar_Click.Name = "BtnGuardar_Click";
            this.BtnGuardar_Click.RightToLeft = System.Windows.Forms.RightToLeft.Yes;
            this.BtnGuardar_Click.Size = new System.Drawing.Size(112, 46);
            this.BtnGuardar_Click.TabIndex = 4;
            this.BtnGuardar_Click.Text = "Guardar";
            this.BtnGuardar_Click.UseVisualStyleBackColor = true;
            // 
            // CotizadorForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(9F, 20F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(1176, 678);
            this.Controls.Add(this.dgvProductos);
            this.Controls.Add(this.panelBottom);
            this.Controls.Add(this.panelTop);
            this.Name = "CotizadorForm";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "Cotizador";
            this.panelTop.ResumeLayout(false);
            this.panelTop.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dgvProductos)).EndInit();
            this.panelBottom.ResumeLayout(false);
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.DataGridViewTextBoxColumn DESCRIPCION;
        private System.Windows.Forms.DataGridViewTextBoxColumn CANTIDAD;
        public System.Windows.Forms.Button BtnGuardar_Click;
    }
}
