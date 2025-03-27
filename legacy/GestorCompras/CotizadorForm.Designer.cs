using System;
using System.Drawing;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    partial class CotizadorForm
    {
        private System.ComponentModel.IContainer components = null;

        private System.Windows.Forms.Panel panelTop;
        private System.Windows.Forms.Panel panelCenter;
        private System.Windows.Forms.Panel panelBottom;

        private System.Windows.Forms.Label lblNumeroTarea;
        private System.Windows.Forms.TextBox txtNumeroTarea;
        private System.Windows.Forms.Label lblCategoria;
        private System.Windows.Forms.ComboBox cmbCategoria;

        private System.Windows.Forms.DataGridView dgvProductos;
        private System.Windows.Forms.DataGridViewTextBoxColumn DESCRIPCION;
        private System.Windows.Forms.DataGridViewTextBoxColumn CANTIDAD;

        private Button btnRegresar;
        private Button btnPegarExcel;
        private Button btnCotKatuk;
        private Button btnCotcorreo;

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
            this.panelTop = new System.Windows.Forms.Panel();
            this.lblNumeroTarea = new System.Windows.Forms.Label();
            this.txtNumeroTarea = new System.Windows.Forms.TextBox();
            this.lblCategoria = new System.Windows.Forms.Label();
            this.cmbCategoria = new System.Windows.Forms.ComboBox();
            this.panelCenter = new System.Windows.Forms.Panel();
            this.dgvProductos = new System.Windows.Forms.DataGridView();
            this.DESCRIPCION = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.CANTIDAD = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.panelBottom = new System.Windows.Forms.Panel();
            this.btnCotKatuk = new System.Windows.Forms.Button();
            this.btnCotcorreo = new System.Windows.Forms.Button();
            this.btnRegresar = new System.Windows.Forms.Button();
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
            this.panelCenter.Size = new System.Drawing.Size(900, 530);
            this.panelCenter.TabIndex = 0;
            // 
            // dgvProductos
            // 
            this.dgvProductos.AutoSizeColumnsMode = System.Windows.Forms.DataGridViewAutoSizeColumnsMode.Fill;
            this.dgvProductos.BackgroundColor = System.Drawing.Color.White;
            this.dgvProductos.ColumnHeadersDefaultCellStyle = dataGridViewCellStyle1;
            this.dgvProductos.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dgvProductos.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.DESCRIPCION,
            this.CANTIDAD});
            this.dgvProductos.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dgvProductos.EnableHeadersVisualStyles = false;
            this.dgvProductos.GridColor = System.Drawing.Color.LightGray;
            this.dgvProductos.Location = new System.Drawing.Point(10, 10);
            this.dgvProductos.Name = "dgvProductos";
            this.dgvProductos.RowHeadersWidth = 62;
            this.dgvProductos.Size = new System.Drawing.Size(880, 510);
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
            // panelBottom
            // 
            this.panelBottom.BackColor = System.Drawing.Color.Gainsboro;
            this.panelBottom.Controls.Add(this.btnCotKatuk);
            this.panelBottom.Controls.Add(this.btnCotcorreo);
            this.panelBottom.Controls.Add(this.btnRegresar);
            this.panelBottom.Dock = System.Windows.Forms.DockStyle.Bottom;
            this.panelBottom.Location = new System.Drawing.Point(0, 540);
            this.panelBottom.Name = "panelBottom";
            this.panelBottom.Size = new System.Drawing.Size(900, 60);
            this.panelBottom.TabIndex = 1;
            // 
            // btnCotKatuk
            // 
            this.btnCotKatuk.Location = new System.Drawing.Point(0, 0);
            this.btnCotKatuk.Name = "btnCotKatuk";
            this.btnCotKatuk.Size = new System.Drawing.Size(75, 23);
            this.btnCotKatuk.TabIndex = 1;
            this.btnCotKatuk.Click += new System.EventHandler(this.btnCotKatuk_Click);
            // 
            // btnCotcorreo
            // 
            this.btnCotcorreo.Location = new System.Drawing.Point(0, 0);
            this.btnCotcorreo.Name = "btnCotcorreo";
            this.btnCotcorreo.Size = new System.Drawing.Size(75, 23);
            this.btnCotcorreo.TabIndex = 2;
            this.btnCotcorreo.Click += new System.EventHandler(this.btnCotcorreo_Click);
            // 
            // btnPegarExcel

            // btnRegresar
            // 
            this.btnRegresar.Location = new System.Drawing.Point(0, 0);
            this.btnRegresar.Name = "btnRegresar";
            this.btnRegresar.Size = new System.Drawing.Size(75, 23);
            this.btnRegresar.TabIndex = 4;
            this.btnRegresar.Click += new System.EventHandler(this.btnRegresar_Click);
            // 
            // CotizadorForm
            // 
            this.BackColor = System.Drawing.Color.White;
            this.ClientSize = new System.Drawing.Size(900, 600);
            this.Controls.Add(this.panelBottom);
            this.Controls.Add(this.panelCenter);
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

        #endregion
    }
}
