using Npgsql;
using System;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    public partial class ProveedoresForm : Form
    {
        private NpgsqlConnection conn;

        public ProveedoresForm()
        {
            InitializeComponent();
            conn = DatabaseHelper.GetConnection();
            LoadCategorias();
        }

        private void LoadCategorias()
        {
            cmbCategoria.Items.Clear();
            using (var cmd = new NpgsqlCommand("SELECT DISTINCT categoria FROM proveedores", conn))
            {
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        cmbCategoria.Items.Add(reader["categoria"].ToString());
                    }
                }
            }
        }

        private void btnBuscar_Click(object sender, EventArgs e)
        {
            //string ruc = txtBuscarRuc.Text;
            using (var cmd = new NpgsqlCommand("SELECT * FROM proveedores WHERE ruc = @ruc", conn))
            {
               // cmd.Parameters.AddWithValue("@ruc", ruc);
                using (var reader = cmd.ExecuteReader())
                {
                    if (reader.Read())
                    {
                        txtRuc.Text = reader["ruc"].ToString();
                        txtNombre.Text = reader["nombre"].ToString();
                        txtCorreo.Text = reader["correo"].ToString();
                        txtCelular.Text = reader["celular"].ToString();
                        cmbCategoria.SelectedItem = reader["categoria"].ToString();
                        txtCodigoNaf.Text = reader["codigo_naf"].ToString();
                    }
                    else
                    {
                        MessageBox.Show("Proveedor no encontrado.");
                    }
                }
            }
        }

        private void btnGuardar_Click(object sender, EventArgs e)
        {
            string query = @"
                INSERT INTO proveedores (ruc, nombre, correo, celular, categoria, codigo_naf)
                VALUES (@ruc, @nombre, @correo, @celular, @categoria, @codigo_naf)
                ON CONFLICT (ruc) DO UPDATE SET
                    nombre = EXCLUDED.nombre,
                    correo = EXCLUDED.correo,
                    celular = EXCLUDED.celular,
                    categoria = EXCLUDED.categoria,
                    codigo_naf = EXCLUDED.codigo_naf;";

            using (var cmd = new NpgsqlCommand(query, conn))
            {
                cmd.Parameters.AddWithValue("@ruc", txtRuc.Text);
                cmd.Parameters.AddWithValue("@nombre", txtNombre.Text);
                cmd.Parameters.AddWithValue("@correo", txtCorreo.Text);
                cmd.Parameters.AddWithValue("@celular", txtCelular.Text);
                cmd.Parameters.AddWithValue("@categoria", cmbCategoria.SelectedItem.ToString());
                cmd.Parameters.AddWithValue("@codigo_naf", string.IsNullOrEmpty(txtCodigoNaf.Text) ? (object)DBNull.Value : txtCodigoNaf.Text);

                cmd.ExecuteNonQuery();
                MessageBox.Show("Proveedor guardado con éxito!");
            }
        }

        private void btnEliminar_Click(object sender, EventArgs e)
        {
            string ruc = txtRuc.Text;
            using (var cmd = new NpgsqlCommand("DELETE FROM proveedores WHERE ruc = @ruc", conn))
            {
                cmd.Parameters.AddWithValue("@ruc", ruc);
                int rowsAffected = cmd.ExecuteNonQuery();
                MessageBox.Show(rowsAffected > 0 ? "Proveedor eliminado!" : "No se encontró el proveedor");
            }
        }

        private void btnRegresar_Click(object sender, EventArgs e)
        {
            Form1 mainForm = new Form1();
            mainForm.Show();
            this.Close();
        }
    }
}