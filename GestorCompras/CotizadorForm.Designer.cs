using System;
using System.Drawing;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    partial class CotizadorForm
    {
        private System.ComponentModel.IContainer components = null;

        private System.Windows.Forms.Panel panelTop;
        private System.Windows.Forms.Panel panelCenter;   // <--- Panel central para la tabla

        private System.Windows.Forms.Label lblNumeroTarea;
        private System.Windows.Forms.TextBox txtNumeroTarea;
        private System.Windows.Forms.Label lblCategoria;
        private System.Windows.Forms.ComboBox cmbCategoria;

        private System.Windows.Forms.DataGridView dgvProductos;
        private System.Windows.Forms.DataGridViewTextBoxColumn DESCRIPCION;
        private System.Windows.Forms.DataGridViewTextBoxColumn CANTIDAD;

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
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle1 = new System.Windows.Forms.DataGridViewCellStyle();
            System.Windows.Forms.DataGridViewCellStyle dataGridViewCellStyle2 = new System.Windows.Forms.DataGridViewCellStyle();
            this.panelTop = new System.Windows.Forms.Panel();
            this.lblNumeroTarea = new System.Windows.Forms.Label();
            this.txtNumeroTarea = new System.Windows.Forms.TextBox();
            this.lblCategoria = new System.Windows.Forms.Label();
            this.cmbCategoria = new System.Windows.Forms.ComboBox();
            this.panelCenter = new System.Windows.Forms.Panel();
            this.dgvProductos = new System.Windows.Forms.DataGridView();
            this.DESCRIPCION = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.CANTIDAD = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.btnRegresar = new System.Windows.Forms.Button();
            this.btnPegarExcel = new System.Windows.Forms.Button();
            this.btnCotKatuk = new System.Windows.Forms.Button();
            this.btnCotcorreo_Click = new System.Windows.Forms.Button();
            this.BtnGuardar_Click = new System.Windows.Forms.Button();
            this.panelBottom = new System.Windows.Forms.Panel();
            this.panelTop.SuspendLayout();
            this.panelCenter.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dgvProductos)).BeginInit();
            this.panelBottom.SuspendLayout();
            this.SuspendLayout();
            // 
            // panelTop
            // 
            this.panelTop.BackColor = System.Drawing.Color.Gainsboro;
            this.panelTop.Controls.Add(this.lblNumeroTarea);
            this.panelTop.Controls.Add(this.txtNumeroTarea);
            this.panelTop.Controls.Add(this.lblCategoria);
            this.panelTop.Controls.Add(this.cmbCategoria);
            this.panelTop.Dock = System.Windows.Forms.DockStyle.Top;
            this.panelTop.Location = new System.Drawing.Point(0, 0);
            this.panelTop.Name = "panelTop";
            this.panelTop.Size = new System.Drawing.Size(900, 70);
            this.panelTop.TabIndex = 2;
            // 
            // lblNumeroTarea
            // 
            this.lblNumeroTarea.AutoSize = true;
            this.lblNumeroTarea.Location = new System.Drawing.Point(20, 25);
            this.lblNumeroTarea.Name = "lblNumeroTarea";
            this.lblNumeroTarea.Size = new System.Drawing.Size(136, 20);
            this.lblNumeroTarea.TabIndex = 0;
            this.lblNumeroTarea.Text = "Número de Tarea:";
            // 
            // txtNumeroTarea
            // 
            this.txtNumeroTarea.Location = new System.Drawing.Point(140, 22);
            this.txtNumeroTarea.Name = "txtNumeroTarea";
            this.txtNumeroTarea.Size = new System.Drawing.Size(180, 26);
            this.txtNumeroTarea.TabIndex = 1;
            // 
            // lblCategoria
            // 
            this.lblCategoria.AutoSize = true;
            this.lblCategoria.Location = new System.Drawing.Point(350, 25);
            this.lblCategoria.Name = "lblCategoria";
            this.lblCategoria.Size = new System.Drawing.Size(82, 20);
            this.lblCategoria.TabIndex = 2;
            this.lblCategoria.Text = "Categoría:";
            // 
            // cmbCategoria
            // 
            this.cmbCategoria.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.cmbCategoria.Location = new System.Drawing.Point(420, 22);
            this.cmbCategoria.Name = "cmbCategoria";
            this.cmbCategoria.Size = new System.Drawing.Size(200, 28);
            this.cmbCategoria.TabIndex = 3;
            // 
            // panelCenter
            // 
            this.panelCenter.BackColor = System.Drawing.Color.White;
            this.panelCenter.Controls.Add(this.dgvProductos);
            this.panelCenter.Dock = System.Windows.Forms.DockStyle.Fill;
            this.panelCenter.Location = new System.Drawing.Point(0, 70);
            this.panelCenter.Name = "panelCenter";
            this.panelCenter.Padding = new System.Windows.Forms.Padding(10);
            this.panelCenter.Size = new System.Drawing.Size(900, 470);
            this.panelCenter.TabIndex = 0;
            // 
            // dgvProductos
            // 
            this.dgvProductos.AutoSizeColumnsMode = System.Windows.Forms.DataGridViewAutoSizeColumnsMode.Fill;
            this.dgvProductos.BackgroundColor = System.Drawing.Color.White;
            dataGridViewCellStyle1.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle1.BackColor = System.Drawing.Color.SteelBlue;
            dataGridViewCellStyle1.Font = new System.Drawing.Font("Microsoft Sans Serif", 8F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            dataGridViewCellStyle1.ForeColor = System.Drawing.Color.White;
            dataGridViewCellStyle1.SelectionBackColor = System.Drawing.SystemColors.Highlight;
            dataGridViewCellStyle1.SelectionForeColor = System.Drawing.SystemColors.HighlightText;
            dataGridViewCellStyle1.WrapMode = System.Windows.Forms.DataGridViewTriState.True;
            this.dgvProductos.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dgvProductos.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvProductos.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.DESCRIPCION,
            this.CANTIDAD});
            dataGridViewCellStyle2.Alignment = System.Windows.Forms.DataGridViewContentAlignment.MiddleLeft;
            dataGridViewCellStyle2.BackColor = System.Drawing.Color.White;
            dataGridViewCellStyle2.Font = new System.Drawing.Font("Microsoft Sans Serif", 8F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            dataGridViewCellStyle2.ForeColor = System.Drawing.Color.Black;
            dataGridViewCellStyle2.SelectionBackColor = System.Drawing.Color.RoyalBlue;
            dataGridViewCellStyle2.SelectionForeColor = System.Drawing.Color.White;
            dataGridViewCellStyle2.WrapMode = System.Windows.Forms.DataGridViewTriState.False;
            this.dgvProductos.DefaultCellStyle = dataGridViewCellStyle2;
            this.dgvProductos.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dgvProductos.EnableHeadersVisualStyles = false;
            this.dgvProductos.GridColor = System.Drawing.Color.LightGray;
            this.dgvProductos.Location = new System.Drawing.Point(10, 10);
            this.dgvProductos.Name = "dgvProductos";
            this.dgvProductos.RowHeadersWidth = 62;
            this.dgvProductos.Size = new System.Drawing.Size(880, 450);
            this.dgvProductos.TabIndex = 0;
            // 
            // DESCRIPCION
            // 
            this.DESCRIPCION.MinimumWidth = 8;
            this.DESCRIPCION.Name = "DESCRIPCION";
            // 
            // CANTIDAD
            // 
            this.CANTIDAD.MinimumWidth = 8;
            this.CANTIDAD.Name = "CANTIDAD";
            // 
            // btnRegresar
            // 
            this.btnRegresar.Location = new System.Drawing.Point(24, 6);
            this.btnRegresar.Name = "btnRegresar";
            this.btnRegresar.Size = new System.Drawing.Size(75, 23);
            this.btnRegresar.TabIndex = 4;
            // 
            // btnPegarExcel
            // 
            this.btnPegarExcel.Location = new System.Drawing.Point(660, 6);
            this.btnPegarExcel.Name = "btnPegarExcel";
            this.btnPegarExcel.Size = new System.Drawing.Size(75, 23);
            this.btnPegarExcel.TabIndex = 3;
            // 
            // btnCotKatuk
            // 
            this.btnCotKatuk.Location = new System.Drawing.Point(523, 6);
            this.btnCotKatuk.Name = "btnCotKatuk";
            this.btnCotKatuk.Size = new System.Drawing.Size(75, 23);
            this.btnCotKatuk.TabIndex = 2;
            // 
            // btnCotcorreo_Click
            // 
            this.btnCotcorreo_Click.Location = new System.Drawing.Point(378, 0);
            this.btnCotcorreo_Click.Name = "btnCotcorreo_Click";
            this.btnCotcorreo_Click.Size = new System.Drawing.Size(75, 23);
            this.btnCotcorreo_Click.TabIndex = 1;
            // 
            // BtnGuardar_Click
            // 
            this.BtnGuardar_Click.Location = new System.Drawing.Point(207, 6);
            this.BtnGuardar_Click.Name = "BtnGuardar_Click";
            this.BtnGuardar_Click.Size = new System.Drawing.Size(75, 23);
            this.BtnGuardar_Click.TabIndex = 0;
            // 
            // panelBottom
            // 
            this.panelBottom.BackColor = System.Drawing.Color.Gainsboro;
            this.panelBottom.Controls.Add(this.BtnGuardar_Click);
            this.panelBottom.Controls.Add(this.btnCotcorreo_Click);
            this.panelBottom.Controls.Add(this.btnCotKatuk);
            this.panelBottom.Controls.Add(this.btnPegarExcel);
            this.panelBottom.Controls.Add(this.btnRegresar);
            this.panelBottom.Dock = System.Windows.Forms.DockStyle.Bottom;
            this.panelBottom.Location = new System.Drawing.Point(0, 540);
            this.panelBottom.Name = "panelBottom";
            this.panelBottom.Size = new System.Drawing.Size(900, 60);
            this.panelBottom.TabIndex = 1;
            // 
            // CotizadorForm
            // 
            this.BackColor = System.Drawing.Color.White;
            this.ClientSize = new System.Drawing.Size(900, 600);
            this.Controls.Add(this.panelCenter);
            this.Controls.Add(this.panelBottom);
            this.Controls.Add(this.panelTop);
            this.Name = "CotizadorForm";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "Cotizador";
            this.panelTop.ResumeLayout(false);
            this.panelTop.PerformLayout();
            this.panelCenter.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)(this.dgvProductos)).EndInit();
            this.panelBottom.ResumeLayout(false);
            this.ResumeLayout(false);

        }

        // ──────────────────────────────────────────────────────────
        // Método para estilizar botones
        // ──────────────────────────────────────────────────────────


        #endregion

        private Button btnRegresar;
        private Button btnPegarExcel;
        private Button btnCotKatuk;
        private Button btnCotcorreo_Click;
        public Button BtnGuardar_Click;
        private Panel panelBottom;
    }
}

