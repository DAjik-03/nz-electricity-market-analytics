let
    Dates = List.Dates(#date(2025,9,1),365,#duration(1,0,0,0)),
    Base = Table.FromColumns({Dates},type table [Date=date]),
    Y = Table.AddColumn(Base,"Year",each Date.Year([Date]),Int64.Type),
    MN = Table.AddColumn(Y,"Month Number",each Date.Month([Date]),Int64.Type),
    M = Table.AddColumn(MN,"Month",each Date.ToText([Date],"MMM","en-NZ"),type text),
    YM = Table.AddColumn(M,"Year-Month",each Date.ToText([Date],"yyyy-MM","en-NZ"),type text),
    YMK = Table.AddColumn(YM,"Year-Month Sort",each [Year]*100+[Month Number],Int64.Type),
    Q = Table.AddColumn(YMK,"Quarter",each "Q" & Text.From(Date.QuarterOfYear([Date])),type text),
    WN = Table.AddColumn(Q,"Weekday Number",each Date.DayOfWeek([Date],Day.Monday)+1,Int64.Type),
    W = Table.AddColumn(WN,"Weekday",each Date.ToText([Date],"ddd","en-NZ"),type text),
    DT = Table.AddColumn(W,"Day Type",each if [Weekday Number]>5 then "Weekend" else "Weekday",type text)
in DT
