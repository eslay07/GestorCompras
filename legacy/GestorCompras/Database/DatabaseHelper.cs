using Microsoft.IdentityModel.Protocols;
using NLog.Internal;
using Npgsql;
using System.Configuration;

public static class DatabaseHelper
{
    public static NpgsqlConnection GetConnection()
    {
        // Aquí no debes usar ConfigurationManager<string>
        string connectionString = ConfigurationManager.ConnectionStrings["DefaultConnection"].ConnectionString;
        NpgsqlConnection conn = new NpgsqlConnection(connectionString);
        conn.Open();
        return conn;
    }
}