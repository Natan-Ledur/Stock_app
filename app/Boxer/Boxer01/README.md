# Módulo Boxer – Controle de Fios

Este módulo é responsável pelo processamento, análise e armazenamento dos dados de controle de fios da empresa.

## Estrutura dos Dados no MongoDB

Os principais DataFrames gerados pelo script `main.py` são salvos em coleções separadas no banco de dados MongoDB. Cada coleção representa um conjunto de dados específico do controle de fios:

- **df_final**: Resultado consolidado do estoque, consumo e pedidos, pronto para uso em dashboards.
- **df_resultado**: DataFrame intermediário com cálculos detalhados de consumo e estoque.
- **df_estoque**: Dados brutos de estoque atual, conforme consulta ao banco de dados principal.
- **df_consumo_produtos**: Informações de consumo por produto, extraídas da tabela de consumo.
- **df_pedidos_setores_grupos**: Dados detalhados dos pedidos por setor e grupo.
- **df_agrupado**: Agrupamento dos pedidos por campos principais, com soma das quantidades.
- **df_agrupado_consumo**: Associação dos pedidos com o consumo por produto.
- **df_soma_consumo**: Soma total do consumo agrupado por pedido, material, cor e setor.

Cada execução do script sobrescreve os dados antigos, mantendo sempre os dados mais recentes para consulta.

## Boas práticas de organização

- Os nomes das coleções seguem o padrão `df_nome` para facilitar a identificação.
- Os campos dos documentos seguem o padrão `snake_case` (minúsculo e com underline).
- Recomenda-se criar índices nos campos mais consultados para melhorar a performance.
- Para histórico ou versionamento, crie coleções com data ou versão, se necessário.

## Atualização dos dados

Os dados são atualizados diariamente (ou conforme necessidade) ao rodar o script `main.py`. O dashboard consome os dados diretamente do MongoDB, sem necessidade de processamento adicional.

## Integração

Este módulo pode ser integrado com outros módulos do projeto Stock_app, mantendo as coleções separadas para cada área (ex: Boxer, Meia, etc).

---

*Para dúvidas ou sugestões sobre o módulo Boxer, consulte o README principal do projeto ou abra uma issue específica.*
