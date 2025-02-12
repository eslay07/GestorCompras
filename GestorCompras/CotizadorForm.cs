using Newtonsoft.Json;
using Npgsql;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
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
            conn = DatabaseHelper.GetConnection();
           dgvProductos.KeyDown += dgvProductos_KeyDown;
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
            string[] filas = clipboardText.Split('\n');

            int rowIndex = dgvProductos.CurrentCell.RowIndex;
            int colIndex = dgvProductos.CurrentCell.ColumnIndex;

            foreach (string fila in filas)
            {
                if (string.IsNullOrWhiteSpace(fila)) continue;

                string[] celdas = fila.Split('\t');
                int tempColIndex = colIndex;

                // Verificar si hay suficientes filas, si no, agregar nuevas
                if (rowIndex >= dgvProductos.Rows.Count - 1)
                {
                    dgvProductos.Rows.Add(); // Agregar fila si es necesario
                }

                foreach (string celda in celdas)
                {
                    if (tempColIndex < dgvProductos.ColumnCount && rowIndex < dgvProductos.RowCount)
                    {
                        dgvProductos[tempColIndex, rowIndex].Value = celda.Trim();
                        tempColIndex++;
                    }
                }
                rowIndex++; // Pasar a la siguiente fila
            }
        }

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
                Arguments = $"\"E:/Proyecto compras/GestorCompras/Cotizador_katuk.py\" \"{jsonPath}\"",
                UseShellExecute = false
            };

            using (Process proc = Process.Start(start))
            {
                proc.WaitForExit(); //n  0'1 Esperar a que termine el script de Python

                //  Eliminar el archivo JSON después de la ejecución
               // if (File.Exists(jsonPath))
                //{
                   // File.Delete(jsonPath);
                    //Console.WriteLine("Archivo JSON eliminado correctamente.");
               // }

                MessageBox.Show("Publicación creada exitosamente!");
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
    }
}