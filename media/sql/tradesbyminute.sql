SELECT
     reference
    ,instrumentName
    ,strftime('%H', th.openDateUtc) trade_hour
    ,profitAndLoss 
FROM trade_history
WHERE transactionType = 'DEAL'