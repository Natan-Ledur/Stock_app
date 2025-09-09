select
    PRODUTO.GRUPO as GRUPO_PROD,
    FACCAO.OP as FAC_OP,
    OF1.DEPOSITO,
    FACCAO.PEDIDO as FAC_PEDIDO,
    FACCAO.CODIGO as FAC_CODIGO,
    FACCAO.COR as FAC_COR,
    FACCAO.TAM as FAC_TAM,
    FACCAO.QT_ORIG as FAC_QT_ORIG,
    (
        select
            SUM(coalesce(OF_ITEN.QTDE, 0))
        from
            OF_ITEN_001 OF_ITEN
        where
            OF_ITEN.NUMERO = FACCAO.NUMERO
            and OF_ITEN.COR = FACCAO.COR
            and OF_ITEN.TAM = FACCAO.TAM
    ) as OF_QTDE_ORIG
from
    FACCAO_001 FACCAO
inner join PRODUTO_001 PRODUTO 
    on (FACCAO.CODIGO = PRODUTO.CODIGO)
left join (
    select
        NUMERO,
        DEPOSITO
    from
        OF1_001
) OF1 on (FACCAO.NUMERO = OF1.NUMERO)
where
    (FACCAO.QT_ORIG - (FACCAO.QUANT + FACCAO.QUANT_2 + FACCAO.QUANT_I + FACCAO.QUANT_F + coalesce(FACCAO.QTDE_EXPURGA, 0))) > 0
    and (FACCAO.OP in ('01','18','19'))
    and (PRODUTO.ETIQUETA in ('02'))
    and PRODUTO.GRUPO IN ('022', '016')
group by
    PRODUTO.GRUPO,
    FACCAO.OP,
    OF1.DEPOSITO,
    FACCAO.PEDIDO,
    FACCAO.CODIGO,
    FACCAO.COR,
    FACCAO.TAM,
    FACCAO.QT_ORIG,
    FACCAO.NUMERO;
