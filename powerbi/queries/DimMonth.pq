let
    M = Table.Distinct(Table.SelectColumns(DimDate,{"Year-Month","Year-Month Sort"})),
    D = Table.AddColumn(M,"MonthStart",each Date.FromText([#"Year-Month"] & "-01"),type date)
in D
