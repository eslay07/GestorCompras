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
using System.Text.Json.Serialization;
using System.Windows.Forms;

namespace ProyectoCotizador
{
    public partial class CotizadorForm : Form
    {
        private NpgsqlConnection conn;

        public CotizadorForm()
        {
            InitializeComponent();
            //estilizador de botones
            // Botones en panelBottom
            EstilizarBoton(this.BtnGuardar_Click, "Guardar", 50);
            EstilizarBoton(this.btnCotcorreo_Click, "Cot. Correo", 220);
            EstilizarBoton(this.btnCotKatuk, "Cotizar Katuk", 390);
            EstilizarBoton(this.btnPegarExcel, "Pegar Excel", 560);
            EstilizarBoton(this.btnRegresar, "Regresar", 730);
            //conexiones y teclaas de la tabla
            conn = DatabaseHelper.GetConnection();
           dgvProductos.KeyDown += dgvProductos_KeyDown;
            ConfigurarDataGridView();
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

        private void ConfigurarDataGridView()
        {
            dgvProductos.Columns.Clear();

            dgvProductos.Columns.Add("Codigo", "Código");
            dgvProductos.Columns.Add("Producto", "Producto");
            dgvProductos.Columns.Add("Precio", "Precio");

            // 🔹 Ajustar el tamaño de las columnas al contenido
            dgvProductos.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.AllCells;

            // 🔹 Ajustar el ancho total del DataGridView según sus columnas
            dgvProductos.Width = dgvProductos.Columns.Cast<DataGridViewColumn>().Sum(c => c.Width) + dgvProductos.RowHeadersWidth + 5;

            // 🔹 Ajustar la altura total del DataGridView
            dgvProductos.Height = Math.Min(600, dgvProductos.RowTemplate.Height * 50 + dgvProductos.ColumnHeadersHeight + 5);

            // 🔹 Centrar el DataGridView en el formulario
            dgvProductos.Left = (this.ClientSize.Width - dgvProductos.Width) / 2;
            dgvProductos.Top = (this.ClientSize.Height - dgvProductos.Height) / 2;

            // 🔹 Agregar 50 filas en blanco al inicio
            for (int i = 0; i < 55; i++)
            {
                dgvProductos.Rows.Add();
            }

            dgvProductos.EditingControlShowing += dgvProductos_EditingControlShowing;
            dgvProductos.KeyDown += dgvProductos_KeyDown;
        }

        // Manejar eventos cuando el usuario empieza a editar una celda
        private void dgvProductos_EditingControlShowing(object sender, DataGridViewEditingControlShowingEventArgs e)
        {
            if (dgvProductos.CurrentCell.ColumnIndex == 0) // Solo en la columna "Código"
            {
                TextBox txt = e.Control as TextBox;
                if (txt != null)
                {
                    txt.KeyDown -= Codigo_KeyDown;  // Evita múltiples suscripciones
                    txt.KeyDown += Codigo_KeyDown;

                    txt.Leave -= Codigo_Leave;  // Evento al salir de la celda
                    txt.Leave += Codigo_Leave;
                }
            }
        }
        // Detectar cambios en la celda "Código" y limpiar si es necesario
        private void dgvProductos_CellValueChanged(object sender, DataGridViewCellEventArgs e)
        {
            if (e.ColumnIndex == 0 && e.RowIndex >= 0) // Solo afecta a la columna "Código"
            {
                string codigo = dgvProductos.Rows[e.RowIndex].Cells["Codigo"].Value?.ToString()?.Trim();

                if (string.IsNullOrEmpty(codigo))
                {
                    // Si el código está vacío, limpiar "Producto" y "Precio"
                    dgvProductos.Rows[e.RowIndex].Cells["Producto"].Value = "";
                    dgvProductos.Rows[e.RowIndex].Cells["Precio"].Value = "";
                }
                else
                {
                    // Si se escribió un código, intentar completar datos
                    CompletarDatosDesdeBD(codigo, e.RowIndex);
                }
            }
        }

        // Cuando el usuario presiona "Enter" en la celda "Código"
        private void Codigo_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter)
            {
                int rowIndex = dgvProductos.CurrentCell.RowIndex;
                string codigo = dgvProductos.Rows[rowIndex].Cells["Codigo"].EditedFormattedValue.ToString().Trim();

                if (!string.IsNullOrEmpty(codigo))
                {
                    CompletarDatosDesdeBD(codigo, rowIndex);
                }

                e.SuppressKeyPress = true; // Evita el sonido del "Enter"
            }
        }

        // Cuando el usuario termina de editar una celda y cambia de foco
        private void Codigo_Leave(object sender, EventArgs e)
        {
            int rowIndex = dgvProductos.CurrentCell.RowIndex;
            string codigo = dgvProductos.Rows[rowIndex].Cells["Codigo"].EditedFormattedValue.ToString().Trim();

            if (string.IsNullOrEmpty(codigo))
            {
                // Si el usuario borra el código, limpiar Producto y Precio
                dgvProductos.Rows[rowIndex].Cells["Producto"].Value = "";
                dgvProductos.Rows[rowIndex].Cells["Precio"].Value = "";
            }
            else
            {
                // Si hay un código ingresado, intentar completar datos
                CompletarDatosDesdeBD(codigo, rowIndex);
            }
        }


        // Consultar PostgreSQL para obtener el producto y el precio según el código
        private void CompletarDatosDesdeBD(string codigo, int rowIndex)
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
                        }
                        else
                        {
                            // Si el código no existe, limpiar las columnas para evitar datos incorrectos
                            dgvProductos.Rows[rowIndex].Cells["Producto"].Value = "";
                            dgvProductos.Rows[rowIndex].Cells["Precio"].Value = "";
                        }
                    }
                }
            }
        }

        // 🔹 Control de teclas (Copiar, Pegar, Borrar)
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

        // 🔹 Copiar selección al portapapeles
        private void CopiarSeleccion()
        {
            if (dgvProductos.SelectedCells.Count > 0)
            {
                StringBuilder sb = new StringBuilder();
                int currentRowIndex = -1;

                foreach (DataGridViewCell cell in dgvProductos.SelectedCells)
                {
                    if (currentRowIndex != cell.RowIndex)
                    {
                        if (sb.Length > 0) sb.AppendLine();
                        currentRowIndex = cell.RowIndex;
                    }
                    else
                    {
                        sb.Append("\t");
                    }
                    sb.Append(cell.Value?.ToString() ?? "");
                }

                Clipboard.SetText(sb.ToString());
            }
        }

        private void PegarDesdePortapapeles()
        {
            if (!Clipboard.ContainsText()) return;

            string clipboardText = Clipboard.GetText();
            string[] filas = clipboardText.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);

            int rowIndex = dgvProductos.CurrentCell.RowIndex; // Fila actual donde se pega el primer dato
            int colIndex = dgvProductos.CurrentCell.ColumnIndex;

            foreach (string fila in filas)
            {
                string[] celdas = fila.Split('\t');
                int tempColIndex = colIndex;

                // Asegurar que haya suficientes filas en el DataGridView antes de asignar valores
                while (rowIndex >= dgvProductos.Rows.Count)
                {
                    dgvProductos.Rows.Add();
                }

                foreach (string celda in celdas)
                {
                    if (tempColIndex < dgvProductos.ColumnCount && rowIndex < dgvProductos.Rows.Count)
                    {
                        dgvProductos[tempColIndex, rowIndex].Value = celda.Trim();
                        tempColIndex++;
                    }
                }

                // Si la primera columna (Código) tiene un valor, completar datos
                string codigo = dgvProductos.Rows[rowIndex].Cells["Codigo"].Value?.ToString();
                if (!string.IsNullOrEmpty(codigo))
                {
                    CompletarDatosDesdeBD(codigo, rowIndex);
                }

                rowIndex++; // Moverse a la siguiente fila
            }

            // 🔹 Asegurar que la última fila siempre quede vacía para futuras inserciones
            if (!EsFilaVacia(dgvProductos.Rows.Count - 1))
            {
                dgvProductos.Rows.Add();
            }
        }

        private bool EsFilaVacia(int rowIndex)
        {
            if (rowIndex < 0 || rowIndex >= dgvProductos.Rows.Count) return false;

            var codigo = dgvProductos.Rows[rowIndex].Cells["Codigo"].Value;
            return codigo == null || string.IsNullOrWhiteSpace(codigo.ToString());
        }

        // 🔹 Borrar celdas seleccionadas con "Delete" o "Backspace"
        private void BorrarSeleccion()
        {
            foreach (DataGridViewCell cell in dgvProductos.SelectedCells)
            {
                if (!cell.ReadOnly)
                {
                    cell.Value = null;
                }
            }
        }

        private void btnCotKatuk_Click(object sender, EventArgs e)
        {
            try
            {
                var productos = new System.Collections.Generic.List<object>();

                foreach (DataGridViewRow row in dgvProductos.Rows)
                {
                    if (!row.IsNewRow)
                    {
                        string codigo = row.Cells["Codigo"].Value?.ToString()?.Trim();
                        string producto = row.Cells["Producto"].Value?.ToString()?.Trim();
                        string cantidad = row.Cells["Cantidad"].Value?.ToString()?.Trim();

                        // Solo agregar filas donde todas las celdas tienen datos
                        if (!string.IsNullOrEmpty(codigo) && !string.IsNullOrEmpty(producto) && !string.IsNullOrEmpty(cantidad))
                        {
                            productos.Add(new
                            {
                                Codigo = codigo,
                                Producto = producto,
                                Cantidad = cantidad
                            });
                        }
                    }
                }

                // Verificar que hay datos para guardar
                if (productos.Count == 0)
                {
                    MessageBox.Show("No hay productos válidos para procesar.", "Advertencia", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }

                var jsonData = new
                {
                    NumeroTarea = txtNumeroTarea.Text.Trim(),
                    Categoria = cmbCategoria.SelectedItem?.ToString()?.Trim(),
                    Productos = productos
                };

                string basePath = Application.StartupPath;
                string jsonPath = Path.Combine(basePath, "datos_automatizacion_temp.json");

                // 🔹 📌 Verificar permisos de escritura
                if (!Directory.Exists(basePath))
                {
                    MessageBox.Show($"Error: La carpeta {basePath} no existe.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }

                // 🔹 📌 Guardar el JSON inicial
                try
                {
                    File.WriteAllText(jsonPath, JsonConvert.SerializeObject(jsonData, Formatting.Indented));
                    MessageBox.Show($"Archivo JSON creado exitosamente en:\n{jsonPath}", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                catch (Exception ex)
                {
                    MessageBox.Show($"Error al escribir el archivo JSON:\n{ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }

                // 🔹 📌 Ejecutar el script de Python
                ProcessStartInfo start = new ProcessStartInfo
                {
                    FileName = "C:\\Users\\jimmy\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
                    Arguments = $"\"E:/Proyecto compras/GestorCompras/Cotizador_katuk.py\" \"{jsonPath}\"",
                    UseShellExecute = false
                };

                using (Process proc = Process.Start(start))
                {
                    proc.WaitForExit(); // Esperar a que termine el script de Python

                    // ********** 📌 LÓGICA PARA CREAR ARCHIVOS CONSECUTIVOS SI EL SCRIPT SIGUE EJECUTÁNDOSE **********
                    /*
                    int count = 1;
                    string newJsonPath = jsonPath;

                    while (Process.GetProcessesByName("python").Length > 0) // Verifica si hay instancias de Python corriendo
                    {
                        newJsonPath = Path.Combine(basePath, $"datos_automatizacion_temp_{count}.json");
                        count++;
                        File.WriteAllText(newJsonPath, JsonConvert.SerializeObject(jsonData, Formatting.Indented));
                    }

                    // Cuando termine el proceso, eliminar archivos temporales
                    foreach (var file in Directory.GetFiles(basePath, "datos_automatizacion_temp_*.json"))
                    {
                        File.Delete(file);
                    }
                    */

                    MessageBox.Show("Publicación creada exitosamente!");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error inesperado:\n{ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }


        private void btnCotcorreo(object sender, EventArgs e)
        {
            var productos = new System.Collections.Generic.List<object>();
            foreach (DataGridViewRow row in dgvProductos.Rows)
            {
                if (!row.IsNewRow)
                {
                    productos.Add(new
                    {
                        Producto = row.Cells[0].Value?.ToString(),
                        Cantidad = row.Cells[1].Value?.ToString()
                    });
                }
            }

            var jsonData = new
            {
                NumeroTarea = txtNumeroTarea.Text,
                Categoria = cmbCategoria.SelectedItem?.ToString(),
                Productos = productos
            };

            string jsonPath = Path.Combine(Application.StartupPath, "datos_automatizacion_temp.json");
            File.WriteAllText(jsonPath, JsonConvert.SerializeObject(jsonData));

            ProcessStartInfo start = new ProcessStartInfo
            {
                FileName = "C:\\Users\\jimmy\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
                Arguments = $"\"E:/Proyecto compras/GestorCompras/busqueda_de_tarea.py\" \"{jsonPath}\"",
                UseShellExecute = false
            };

            using (Process proc = Process.Start(start))
            {
                proc.WaitForExit(); // Esperar a que termine el script de Python

                //  Eliminar el archivo JSON después de la ejecución
                if (File.Exists(jsonPath))
                {
                    File.Delete(jsonPath);
                    Console.WriteLine("Archivo JSON eliminado correctamente.");
                }

                MessageBox.Show("Publicación creada exitosamente!");
            }
        } 
   
        //prueba para commit
        private void btnRegresar_Click(object sender, EventArgs e)
        {
            Form1 mainForm = new Form1();
            mainForm.Show();
            this.Close();
        }

        private void dgvProductos_CellContentClick(object sender, DataGridViewCellEventArgs e)
        {

        }

        private void dgvProductos_CellContentClick_1(object sender, DataGridViewCellEventArgs e)
        {

        }
        private void EstilizarBoton(Button boton, string texto, int posicionX)
        {
            boton.Text = texto;
            boton.Size = new System.Drawing.Size(140, 35);
            boton.Location = new Point(posicionX, 12);

            boton.ForeColor = Color.White;
            boton.BackColor = Color.SteelBlue;
            boton.FlatStyle = FlatStyle.Flat;
            boton.FlatAppearance.BorderSize = 0;
        }

    }
}