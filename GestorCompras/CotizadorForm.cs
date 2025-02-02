using Newtonsoft.Json;
using Npgsql;
using System;
using System.Diagnostics;
using System.IO;
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
            LoadCategorias();
        }

        private void LoadCategorias()
        {
            //cmbCategoria.Items.Clear();
            using (var cmd = new NpgsqlCommand("SELECT DISTINCT categoria FROM proveedores", conn))
            {
                using (var reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                       // cmbCategoria.Items.Add(reader["categoria"].ToString());
                    }
                }
            }
        }

        private void btnPegarExcel_Click(object sender, EventArgs e)
        {
            if (Clipboard.ContainsData(DataFormats.Text))
            {
                string clipboardText = Clipboard.GetText();
                string[] filas = clipboardText.Split('\n');
                foreach (string fila in filas)
                {
                    if (!string.IsNullOrWhiteSpace(fila))
                    {
                        string[] celdas = fila.Split('\t');
                        //dgvProductos.Rows.Add(celdas[0], celdas[1]);
                    }
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
                FileName = "python",
                Arguments = $"ScriptsPython/katuk.py \"{jsonPath}\"",
                UseShellExecute = false
            };

            using (Process proc = Process.Start(start))
            {
                proc.WaitForExit();
                MessageBox.Show("Publicación creada exitosamente!");
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