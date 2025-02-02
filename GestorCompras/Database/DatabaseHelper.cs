using Npgsql;
using System.Configuration;

public static class DatabaseHelper
{
    public static NpgsqlConnection GetConnection()
    {
        string connectionString = ConfigurationManager.ConnectionStrings["DefaultConnection"].ConnectionString;
        NpgsqlConnection conn = new NpgsqlConnection(connectionString);
        conn.Open();
        return conn;
    }
}