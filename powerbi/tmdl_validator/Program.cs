using Microsoft.AnalysisServices.Tabular;
using System.Text.Json;

// Parse metadata only. Never connect to a database or execute a model update.
var database = TmdlSerializer.DeserializeDatabaseFromFolder(Path.GetFullPath(args[0]));
var model = database.Model;
var result = new {
    parser = typeof(TmdlSerializer).Assembly.FullName,
    tables = model.Tables.Count,
    expressions = model.Expressions.Count,
    relationships = model.Relationships.Count,
    measures = model.Tables.Sum(t => t.Measures.Count),
    columns = model.Tables.Sum(t => t.Columns.Count),
    tableNames = model.Tables.Select(t => t.Name).ToArray()
};
if (result.tables != 16 || result.expressions != 4 || result.relationships != 8 || result.measures != 59)
    throw new Exception("Approved object counts do not match.");
Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
