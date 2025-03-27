using Newtonsoft.Json;
using Npgsql;
using System;
using System.Collections.Generic;
using System.Data;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    public partial class CotizadorForm : Form
    {
        private NpgsqlConnection conn;

        public CotizadorForm()
        {
            InitializeComponent();

            // Estilizar botones
       
            EstilizarBoton(this.btnCotcorreo, "Cot. Correo", 220);
            EstilizarBoton(this.btnCotKatuk, "Cotizar Katuk", 390);
            EstilizarBoton(this.btnRegresar, "Regresar", 730);

            // Configuración del DataGridView
            conn = DatabaseHelper.GetConnection();
            dgvProductos.KeyDown += dgvProductos_KeyDown;
            dgvProductos.EditingControlShowing += dgvProductos_EditingControlShowing;
            dgvProductos.RowsAdded += dgvProductos_RowsAdded;
            ConfigurarDataGridView();
            LoadCategorias();
        }

        private void LoadCategorias()
        {
            cmbCategoria.Items.Clear();
            if (conn.State != ConnectionState.Open)
            {
                conn.Open();
            }
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

        private void ConfigurarDataGridView()
        {
            dgvProductos.Columns.Clear();
            dgvProductos.Columns.Add("Codigo", "Código");
            dgvProductos.Columns.Add("Producto", "Producto");
            dgvProductos.Columns.Add("Cantidad", "Cantidad"); // Editable por el usuario
            dgvProductos.Columns.Add("Precio", "Precio");

            dgvProductos.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.AllCells;

            // Agregar una fila inicial + 2 filas en blanco
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
            dgvProductos.Rows.Add();
        }

        private void dgvProductos_EditingControlShowing(object sender, DataGridViewEditingControlShowingEventArgs e)
        {
            if (dgvProductos.CurrentCell.ColumnIndex == 0) // Columna "Código"
            {
                TextBox txt = e.Control as TextBox;
                if (txt != null)
                {
                    txt.KeyDown -= Codigo_KeyDown;
                    txt.KeyDown += Codigo_KeyDown;
                }
            }
        }
        private void dgvProductos_RowsAdded(object sender, DataGridViewRowsAddedEventArgs e)
        {
            // Si el usuario agrega una nueva fila manualmente, añadimos dos filas más en blanco.
            if (e.RowIndex == dgvProductos.Rows.Count - 1)
            {
                dgvProductos.Rows.Add();
                dgvProductos.Rows.Add();
            }
        }

        private void BorrarSeleccion()
        {
            foreach (DataGridViewCell cell in dgvProductos.SelectedCells)
            {
                cell.Value = DBNull.Value; // Elimina el contenido sin dejar espacios invisibles
            }
        }

        private void dgvProductos_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.Control && e.KeyCode == Keys.C)
            {
                CopiarSeleccion();
                e.Handled = true;
            }
            else if (e.Control && e.KeyCode == Keys.V)
            {
                PegarDesdePortapapeles();
                e.Handled = true;
            }
            else if (e.KeyCode == Keys.Delete || e.KeyCode == Keys.Back)
            {
                BorrarSeleccion();
                e.Handled = true;
            }
        }


        private void Codigo_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter)
            {
                int rowIndex = dgvProductos.CurrentCell.RowIndex;
                string codigo = dgvProductos.Rows[rowIndex].Cells["Codigo"].EditedFormattedValue.ToString().Trim();

                if (!string.IsNullOrEmpty(codigo))
                {
                    bool encontrado = CompletarDatosDesdeBD(codigo, rowIndex);

                    // Si el código no existe, dejar la fila editable
                    if (!encontrado)
                    {
                        dgvProductos.Rows[rowIndex].Cells["Producto"].ReadOnly = false;
                        dgvProductos.Rows[rowIndex].Cells["Cantidad"].ReadOnly = false;
                        dgvProductos.Rows[rowIndex].Cells["Precio"].ReadOnly = false;
                    }

                    // Asegurar que haya exactamente dos filas vacías al final
                    AgregarFilasSiEsNecesario();
                }

                e.SuppressKeyPress = true;
            }
        }



        private bool CompletarDatosDesdeBD(string codigo, int rowIndex)
        {
            string query = "SELECT nombre, precio FROM productos WHERE codigo = @codigo";

            using (var conn = DatabaseHelper.GetConnection())
            {
                if (conn.State != ConnectionState.Open)
                {
                    conn.Open();
                }

                using (var cmd = new NpgsqlCommand(query, conn))
                {
                    cmd.Parameters.AddWithValue("@codigo", codigo);

                    using (var reader = cmd.ExecuteReader())
                    {
                        if (reader.Read())
                        {
                            dgvProductos.Rows[rowIndex].Cells["Producto"].Value = reader["nombre"].ToString();
                            dgvProductos.Rows[rowIndex].Cells["Precio"].Value = reader["precio"].ToString();

                            dgvProductos.Rows[rowIndex].Cells["Producto"].ReadOnly = true;
                            dgvProductos.Rows[rowIndex].Cells["Cantidad"].ReadOnly = false; // El usuario siempre debe ingresar cantidad
                            dgvProductos.Rows[rowIndex].Cells["Precio"].ReadOnly = true;

                            return true; // Código encontrado en BD
                        }
                    }
                }
            }

            return false; // Código no encontrado en BD
        }

        private bool EsFilaVacia(int rowIndex)
        {
            if (rowIndex < 0 || rowIndex >= dgvProductos.Rows.Count) return false;

            var codigo = dgvProductos.Rows[rowIndex].Cells["Codigo"].Value;
            var producto = dgvProductos.Rows[rowIndex].Cells["Producto"].Value;
            var cantidad = dgvProductos.Rows[rowIndex].Cells["Cantidad"].Value;
            var precio = dgvProductos.Rows[rowIndex].Cells["Precio"].Value;

            return (codigo == null || string.IsNullOrWhiteSpace(codigo.ToString())) &&
                   (producto == null || string.IsNullOrWhiteSpace(producto.ToString())) &&
                   (cantidad == null || string.IsNullOrWhiteSpace(cantidad.ToString())) &&
                   (precio == null || string.IsNullOrWhiteSpace(precio.ToString()));
        }
        private void AgregarFilasSiEsNecesario()
        {
            int filasVacias = 0;
            int totalFilas = dgvProductos.Rows.Count;

            // Contamos cuántas filas vacías hay al final
            for (int i = totalFilas - 1; i >= 0; i--)
            {
                if (EsFilaVacia(i))
                {
                    filasVacias++;
                }
                else
                {
                    break; // Detenemos el conteo cuando encontramos una fila con datos
                }
            }

            // Si hay menos de dos filas vacías, agregamos las que falten
            while (filasVacias < 15)
            {
                dgvProductos.Rows.Add();
                filasVacias++;
            }
        }


        private void btnCotKatuk_Click(object sender, EventArgs e)
        {
            GuardarDatosEnJson("Cotizador_katuk.py");
        }

        private void btnCotcorreo_Click(object sender, EventArgs e)
        {
            GuardarDatosEnJson2("busqueda_de_tarea.py");
        }
        ////funcion  que ejecuta script para cotizacion por katuk
        private void GuardarDatosEnJson(string scriptPython)
        {
            string numeroTarea = txtNumeroTarea.Text.Trim();
            string categoria = cmbCategoria.SelectedItem?.ToString()?.Trim();

            // 🔴 Validación de "Número de Tarea" y "Categoría"
            if (string.IsNullOrEmpty(numeroTarea))
            {
                MessageBox.Show("El campo 'Número de Tarea' no puede estar vacío.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (string.IsNullOrEmpty(categoria))
            {
                MessageBox.Show("El campo 'Categoría' no puede estar vacío.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var productos = new List<object>();

            foreach (DataGridViewRow row in dgvProductos.Rows)
            {
                if (row.IsNewRow) continue; // Ignorar la última fila vacía por defecto

                string codigo = row.Cells["Codigo"].Value?.ToString()?.Trim();
                string producto = row.Cells["Producto"].Value?.ToString()?.Trim();
                string cantidad = row.Cells["Cantidad"].Value?.ToString()?.Trim();
                string precio = row.Cells["Precio"].Value?.ToString()?.Trim();

                // 🔴 Validación de filas con código pero con campos vacíos
                if (!string.IsNullOrEmpty(codigo) && (string.IsNullOrEmpty(producto) || string.IsNullOrEmpty(cantidad) || string.IsNullOrEmpty(precio)))
                {
                    MessageBox.Show($"Faltan campos por llenar en la fila del código: {codigo}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return; // No permite guardar el JSON
                }

                // 🔵 Si la fila está completamente vacía, se ignora
                if (string.IsNullOrEmpty(codigo) && string.IsNullOrEmpty(producto) && string.IsNullOrEmpty(cantidad) && string.IsNullOrEmpty(precio))
                {
                    continue;
                }

                // 🔵 Si la fila está completa, agregarla a la lista
                productos.Add(new
                {
                    Codigo = string.IsNullOrEmpty(codigo) ? "SIN CÓDIGO" : codigo,
                    Producto = string.IsNullOrEmpty(producto) ? "SIN PRODUCTO" : producto,
                    Cantidad = string.IsNullOrEmpty(cantidad) ? "0" : cantidad,
                    Precio = string.IsNullOrEmpty(precio) ? "0.00" : precio
                });
            }

            // 🔴 Validación de que haya al menos un producto en la lista
            if (productos.Count == 0)
            {
                MessageBox.Show("No hay productos válidos para procesar.", "Advertencia", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var jsonData = new
            {
                NumeroTarea = numeroTarea,
                Categoria = categoria,
                Productos = productos
            };

            string jsonPath = Path.Combine(Application.StartupPath, "datos_automatizacion_temp.json");
            File.WriteAllText(jsonPath, JsonConvert.SerializeObject(jsonData, Formatting.Indented));

            // COMENTADO PARA FUTURA ACTIVACIÓN
            /*
            Process.Start(new ProcessStartInfo
            {
                FileName = "C:\\Users\\jimmy\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
                Arguments = $"\"E:/Proyecto compras/GestorCompras/{scriptPython}\" \"{jsonPath}\"",
                UseShellExecute = false
            })?.WaitForExit();

            File.Delete(jsonPath);
            */

            MessageBox.Show("Datos listos para automatización. Ejecución de script desactivada.", "Información", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        //funcion  que ejecuta script para cotizacion por correo
        private void GuardarDatosEnJson2(string scriptPython)
        {
            string numeroTarea = txtNumeroTarea.Text.Trim();
            string categoria = cmbCategoria.SelectedItem?.ToString()?.Trim();

            // 🔴 Validación de "Número de Tarea" y "Categoría"
            if (string.IsNullOrEmpty(numeroTarea))
            {
                MessageBox.Show("El campo 'Número de Tarea' no puede estar vacío.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (string.IsNullOrEmpty(categoria))
            {
                MessageBox.Show("El campo 'Categoría' no puede estar vacío.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var productos = new List<object>();

            foreach (DataGridViewRow row in dgvProductos.Rows)
            {
                if (row.IsNewRow) continue; // Ignorar la última fila vacía por defecto

                string codigo = row.Cells["Codigo"].Value?.ToString()?.Trim();
                string producto = row.Cells["Producto"].Value?.ToString()?.Trim();
                string cantidad = row.Cells["Cantidad"].Value?.ToString()?.Trim();
                string precio = row.Cells["Precio"].Value?.ToString()?.Trim();

                // 🔴 Validación de filas con código pero con campos vacíos
                if (!string.IsNullOrEmpty(codigo) && (string.IsNullOrEmpty(producto) || string.IsNullOrEmpty(cantidad) || string.IsNullOrEmpty(precio)))
                {
                    MessageBox.Show($"Faltan campos por llenar en la fila del código: {codigo}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return; // No permite guardar el JSON
                }

                // 🔵 Si la fila está completamente vacía, se ignora
                if (string.IsNullOrEmpty(codigo) && string.IsNullOrEmpty(producto) && string.IsNullOrEmpty(cantidad) && string.IsNullOrEmpty(precio))
                {
                    continue;
                }

                // 🔵 Si la fila está completa, agregarla a la lista
                productos.Add(new
                {
                    Codigo = string.IsNullOrEmpty(codigo) ? "SIN CÓDIGO" : codigo,
                    Producto = string.IsNullOrEmpty(producto) ? "SIN PRODUCTO" : producto,
                    Cantidad = string.IsNullOrEmpty(cantidad) ? "0" : cantidad,
                    Precio = string.IsNullOrEmpty(precio) ? "0.00" : precio
                });
            }

            // 🔴 Validación de que haya al menos un producto en la lista
            if (productos.Count == 0)
            {
                MessageBox.Show("No hay productos válidos para procesar.", "Advertencia", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var jsonData = new
            {
                NumeroTarea = numeroTarea,
                Categoria = categoria,
                Productos = productos
            };

            string jsonPath = Path.Combine(Application.StartupPath, "datos_automatizacion_temp.json");
            File.WriteAllText(jsonPath, JsonConvert.SerializeObject(jsonData, Formatting.Indented));

            // COMENTADO PARA FUTURA ACTIVACIÓN
            /*
            Process.Start(new ProcessStartInfo
            {
                FileName = "C:\\Users\\jimmy\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
                Arguments = $"\"E:/Proyecto compras/GestorCompras/{scriptPython}\" \"{jsonPath}\"",
                UseShellExecute = false
            })?.WaitForExit();

            File.Delete(jsonPath);
            */

            MessageBox.Show("Datos listos para automatización. Ejecución de script desactivada.", "Información", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }




        private void CopiarSeleccion()
        {
            Clipboard.SetText(dgvProductos.GetClipboardContent().GetText());
        }

        private void PegarDesdePortapapeles()
        {
            if (!Clipboard.ContainsText()) return;

            string clipboardText = Clipboard.GetText();
            string[] filas = clipboardText.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);

            int rowIndex = dgvProductos.CurrentCell.RowIndex; // Fila donde se pegarán los datos
            int colIndex = dgvProductos.CurrentCell.ColumnIndex; // Columna seleccionada

            foreach (string fila in filas)
            {
                string[] celdas = fila.Split('\t');
                int tempColIndex = colIndex;

                // Asegurar que haya suficientes filas para pegar los datos
                while (rowIndex >= dgvProductos.Rows.Count)
                {
                    dgvProductos.Rows.Add();
                }

                // Pegado respetando la columna seleccionada
                foreach (string celda in celdas)
                {
                    if (tempColIndex < dgvProductos.ColumnCount) // Evitar que sobrepase las columnas
                    {
                        dgvProductos.Rows[rowIndex].Cells[tempColIndex].Value = celda.Trim();
                        tempColIndex++;
                    }
                }

                // Si se pegó un código, intentar completar datos desde la BD
                string codigo = dgvProductos.Rows[rowIndex].Cells["Codigo"].Value?.ToString();
                if (!string.IsNullOrEmpty(codigo))
                {
                    CompletarDatosDesdeBD(codigo, rowIndex);
                }

                rowIndex++;
            }

            // Asegurar que haya dos filas vacías al final después de pegar datos
            AgregarFilasSiEsNecesario();
        }



        private void btnRegresar_Click(object sender, EventArgs e)
        {
            new Form1().Show();
            this.Close();
        }

        private void EstilizarBoton(Button boton, string texto, int posicionX)
        {
            boton.Text = texto;
            boton.Size = new Size(140, 35);
            boton.Location = new Point(posicionX, 12);
            boton.ForeColor = Color.White;
            boton.BackColor = Color.SteelBlue;
            boton.FlatStyle = FlatStyle.Flat;
            boton.FlatAppearance.BorderSize = 0;
        }
    }
}
