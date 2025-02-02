namespace ProyectoCotizador
{
    partial class CotizadorForm
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
            this.dgvProductos = new System.Windows.Forms.DataGridView();
            this.productoCelda = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.cantidadCelda = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.btnPegarExcel = new System.Windows.Forms.Button();
            this.cmbCategoria = new System.Windows.Forms.ComboBox();
            this.txtNumeroTarea = new System.Windows.Forms.TextBox();
            this.label7 = new System.Windows.Forms.Label();
            this.label8 = new System.Windows.Forms.Label();
            this.btnCotKatuk = new System.Windows.Forms.Button();
            this.btnCotCorreo = new System.Windows.Forms.Button();
            this.btnRegresar = new System.Windows.Forms.Button();
            ((System.ComponentModel.ISupportInitialize)(this.dgvProductos)).BeginInit();
            this.SuspendLayout();
            // 
            // dgvProductos
            // 
            this.dgvProductos.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvProductos.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.productoCelda,
            this.cantidadCelda});
            this.dgvProductos.Location = new System.Drawing.Point(56, 188);
            this.dgvProductos.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.dgvProductos.Name = "dgvProductos";
            this.dgvProductos.RowHeadersWidth = 62;
            this.dgvProductos.Size = new System.Drawing.Size(450, 250);
            this.dgvProductos.TabIndex = 0;
            // 
            // productoCelda
            // 
            this.productoCelda.HeaderText = "Producto";
            this.productoCelda.MinimumWidth = 8;
            this.productoCelda.Name = "productoCelda";
            this.productoCelda.Width = 150;
            // 
            // cantidadCelda
            // 
            this.cantidadCelda.HeaderText = "Cantidad";
            this.cantidadCelda.MinimumWidth = 8;
            this.cantidadCelda.Name = "cantidadCelda";
            this.cantidadCelda.Width = 150;
            // 
            // btnPegarExcel
            // 
            this.btnPegarExcel.BackColor = System.Drawing.Color.Teal;
            this.btnPegarExcel.Font = new System.Drawing.Font("Arial", 10F, System.Drawing.FontStyle.Bold);
            this.btnPegarExcel.ForeColor = System.Drawing.Color.White;
            this.btnPegarExcel.Location = new System.Drawing.Point(512, 274);
            this.btnPegarExcel.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnPegarExcel.Name = "btnPegarExcel";
            this.btnPegarExcel.Size = new System.Drawing.Size(169, 74);
            this.btnPegarExcel.TabIndex = 1;
            this.btnPegarExcel.Text = "Pegar desde Excel";
            this.btnPegarExcel.UseVisualStyleBackColor = false;
            // 
            // cmbCategoria
            // 
            this.cmbCategoria.Location = new System.Drawing.Point(370, 132);
            this.cmbCategoria.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.cmbCategoria.Name = "cmbCategoria";
            this.cmbCategoria.Size = new System.Drawing.Size(136, 28);
            this.cmbCategoria.TabIndex = 2;
            // 
            // txtNumeroTarea
            // 
            this.txtNumeroTarea.Location = new System.Drawing.Point(219, 132);
            this.txtNumeroTarea.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.txtNumeroTarea.Name = "txtNumeroTarea";
            this.txtNumeroTarea.Size = new System.Drawing.Size(112, 26);
            this.txtNumeroTarea.TabIndex = 3;
            // 
            // label7
            // 
            this.label7.Location = new System.Drawing.Point(0, 0);
            this.label7.Name = "label7";
            this.label7.Size = new System.Drawing.Size(112, 29);
            this.label7.TabIndex = 4;
            // 
            // label8
            // 
            this.label8.Location = new System.Drawing.Point(0, 0);
            this.label8.Name = "label8";
            this.label8.Size = new System.Drawing.Size(112, 29);
            this.label8.TabIndex = 5;
            // 
            // btnCotKatuk
            // 
            this.btnCotKatuk.Location = new System.Drawing.Point(0, 0);
            this.btnCotKatuk.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnCotKatuk.Name = "btnCotKatuk";
            this.btnCotKatuk.Size = new System.Drawing.Size(84, 29);
            this.btnCotKatuk.TabIndex = 6;
            // 
            // btnCotCorreo
            // 
            this.btnCotCorreo.Location = new System.Drawing.Point(0, 0);
            this.btnCotCorreo.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnCotCorreo.Name = "btnCotCorreo";
            this.btnCotCorreo.Size = new System.Drawing.Size(84, 29);
            this.btnCotCorreo.TabIndex = 7;
            // 
            // btnRegresar
            // 
            this.btnRegresar.Location = new System.Drawing.Point(0, 0);
            this.btnRegresar.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.btnRegresar.Name = "btnRegresar";
            this.btnRegresar.Size = new System.Drawing.Size(84, 29);
            this.btnRegresar.TabIndex = 8;
            // 
            // CotizadorForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(9F, 20F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.White;
            this.ClientSize = new System.Drawing.Size(675, 750);
            this.Controls.Add(this.dgvProductos);
            this.Controls.Add(this.btnPegarExcel);
            this.Controls.Add(this.cmbCategoria);
            this.Controls.Add(this.txtNumeroTarea);
            this.Controls.Add(this.label7);
            this.Controls.Add(this.label8);
            this.Controls.Add(this.btnCotKatuk);
            this.Controls.Add(this.btnCotCorreo);
            this.Controls.Add(this.btnRegresar);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedSingle;
            this.Margin = new System.Windows.Forms.Padding(3, 4, 3, 4);
            this.Name = "CotizadorForm";
            this.Text = "Cotizador";
            ((System.ComponentModel.ISupportInitialize)(this.dgvProductos)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();

        }
        #endregion

        private System.Windows.Forms.DataGridView dgvProductos;
        private System.Windows.Forms.DataGridViewTextBoxColumn productoCelda;
        private System.Windows.Forms.DataGridViewTextBoxColumn cantidadCelda;
        private System.Windows.Forms.Button btnPegarExcel;
        private System.Windows.Forms.ComboBox cmbCategoria;
        private System.Windows.Forms.TextBox txtNumeroTarea;
        private System.Windows.Forms.Label label7;
        private System.Windows.Forms.Label label8;
        private System.Windows.Forms.Button btnCotKatuk;
        private System.Windows.Forms.Button btnCotCorreo;
        private System.Windows.Forms.Button btnRegresar;
    }
}