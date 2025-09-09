-- SQL FIOS

SELECT
    mat.codigo,
    mat.descricao,
    est.cor,
    mat.grupo,
    mat.sub_grupo,
    mat.ativo,
    est.deposito,
    cor.descricao AS descricao_cor,
    cor.codigo2 AS codigo_tabela_cor,
    SUM(est.qtde) AS estoque_total
FROM material_001 mat
    INNER JOIN mat_iten_001 est ON mat.codigo = est.codigo
    INNER JOIN cadcor_001 cor ON cor.cor = est.cor
    INNER JOIN subgrupo_ma_001 subg ON subg.codigo = mat.sub_grupo
    INNER JOIN grupo_ma_001 gp ON gp.codigo = mat.grupo
WHERE mat.grupo = :GRUPO
    AND est.deposito IN (:DEPOSITO)
GROUP BY 
    mat.codigo, 
    mat.descricao,
    est.cor,
    mat.grupo,
    gp.descricao,
    mat.sub_grupo,
    subg.descricao,
    mat.ativo,
    est.deposito,
    cor.descricao,
    cor.codigo2