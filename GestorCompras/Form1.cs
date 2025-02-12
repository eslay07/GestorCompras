//using Cotizador;
using GestorCompras;
using System;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
        }

        private void btnProveedores_Click(object sender, EventArgs e)
        {
            ProveedoresForm proveedoresForm = new ProveedoresForm();
            proveedoresForm.Show();
            this.Hide();
        }

        private void btnProductos_Click(object sender, EventArgs e)
        {
            ProductosForm productosForm = new ProductosForm();
            productosForm.Show();
            this.Hide();
        }



        private void btnCotizador_Click(object sender, EventArgs e)
        {
            CotizadorForm cotizadorForm = new CotizadorForm();
            cotizadorForm.Show();
            this.Hide();
        }

        private void btnTareas_Click(object sender, EventArgs e)
        {
            TareasForm tareasForm = new TareasForm();
            tareasForm.Show();
            this.Hide();
        }

        private void btnSalir_Click(object sender, EventArgs e)
        {
            Application.Exit();
        }

        private void label1_Click(object sender, EventArgs e)
        {

        }
    }
}