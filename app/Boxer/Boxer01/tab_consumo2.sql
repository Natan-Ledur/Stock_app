select 
		c.material,
		c.cor_prod,
		c.cor_insumo,
		c.produto,
		c.setor,
		c.tam,
		c.tam as tam2,
		c.consumo,
		prod.categoria,
		prod.codigo,
		prod.unidade,
		prod.descricao,  
		cc.descricao 
	from consumoprod c 
INNER JOIN produto_001 prod ON c.produto = prod.codigo
inner join cadcor_001 cc on c.cor_insumo = cc.cor 
--inner join PRODUTO_001 P on c.produto =  p.codigo

