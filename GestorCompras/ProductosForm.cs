using Npgsql;
using System;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    public partial class ProductosForm : Form
    {
        private NpgsqlConnection conn;

        public ProductosForm()
        {
            InitializeComponent();
            conn = DatabaseHelper.GetConnection();
        }
        //454
        private void btnBuscar_Click(object sender, EventArgs e)
        {
            string codigo = txtCodigoBuscar.Text.Trim();
            if (string.IsNullOrEmpty(codigo))
            {
                MessageBox.Show("Ingrese un código de producto.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            BuscarProducto(codigo);
        }

        private void BuscarProducto(string codigo)
        {
            using (var cmd = new NpgsqlCommand("SELECT * FROM Productos WHERE codigo = @codigo", conn))
            {
                cmd.Parameters.AddWithValue("@codigo", codigo);
                using (var reader = cmd.ExecuteReader())
                {
                    if (reader.Read())
                    {
                        txtCodigo.Text = reader["codigo"].ToString();
                        txtNombre.Text = reader["nombre"].ToString();
                        txtCategoria.Text = reader["categoria"].ToString();
                        txtPrecio.Text = reader["precio"].ToString();
                    }
                    else
                    {
                        MessageBox.Show("Producto no encontrado.", "Información", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    }
                }
            }
        }

        private void btnModificar_Click(object sender, EventArgs e)
        {
            if (string.IsNullOrEmpty(txtCodigo.Text))
            {
                MessageBox.Show("Debe buscar un producto antes de modificar.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            using (var cmd = new NpgsqlCommand("UPDATE Productos SET nombre = @nombre, categoria = @categoria, precio = @precio WHERE codigo = @codigo", conn))
            {
                cmd.Parameters.AddWithValue("@codigo", txtCodigo.Text.Trim());
                cmd.Parameters.AddWithValue("@nombre", txtNombre.Text.Trim());
                cmd.Parameters.AddWithValue("@categoria", txtCategoria.Text.Trim());
                cmd.Parameters.AddWithValue("@precio", decimal.Parse(txtPrecio.Text.Trim()));

                int rowsAffected = cmd.ExecuteNonQuery();
                if (rowsAffected > 0)
                    MessageBox.Show("Producto actualizado correctamente.", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);
                else
                    MessageBox.Show("No se pudo actualizar el producto.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void btnAgregar_Click(object sender, EventArgs e)
        {
            try
            {
                using (var cmd = new NpgsqlCommand("INSERT INTO Productos (codigo, nombre, categoria, precio) VALUES (@codigo, @nombre, @categoria, @precio)", conn))
                {
                    cmd.Parameters.AddWithValue("@codigo", txtCodigo.Text.Trim());
                    cmd.Parameters.AddWithValue("@nombre", txtNombre.Text.Trim());
                    cmd.Parameters.AddWithValue("@categoria", txtCategoria.Text.Trim());
                    cmd.Parameters.AddWithValue("@precio", decimal.Parse(txtPrecio.Text.Trim()));

                    int rowsAffected = cmd.ExecuteNonQuery();
                    if (rowsAffected > 0)
                    {
                        MessageBox.Show("Producto agregado correctamente.", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);
                        LimpiarCampos();
                    }
                    else
                    {
                        MessageBox.Show("No se pudo agregar el producto.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }
                }
            }
            catch (PostgresException ex) when (ex.SqlState == "23505") // Código de error para clave duplicada
            {
                MessageBox.Show("El código ya se encuentra registrado.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Ocurrió un error inesperado: " + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
        private void btnRegresar_Click(object sender, EventArgs e)
        {
            Form1 mainForm = new Form1();
            mainForm.Show();
            this.Close();
        }


        private void LimpiarCampos()
        {
            txtCodigo.Text = "";
            txtNombre.Text = "";
            txtCategoria.Text = "";
            txtPrecio.Text = "";
        }
    }
}
