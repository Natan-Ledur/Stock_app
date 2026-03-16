select 
	    pc.insumo as material,
		c.cor_prod,
		c.cor_insumo,
		c.produto,
		c.setor,
		pc.faixa as tam,
		pc.tam_prod as tam2,
		c.consumo,
		prod.categoria,
		pc.insumo as codigo,
		prod.unidade,
		prod.descricao,  
		cc.descricao
	from consumoprod c 
INNER JOIN produto_001 prod ON c.produto = prod.codigo
inner join cadcor_001 cc on c.cor_insumo = cc.cor 
--inner join PRODUTO_001 P on c.produto =  p.codigo
inner join PCPFT2_001 Pc on c.produto  = pc.codigo and c.tam = pc.tam_prod 
where  pc.tipo = 'P'