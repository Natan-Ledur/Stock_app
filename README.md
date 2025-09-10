
# Stock_app

Este projeto tem como objetivo principal possibilitar a **simulação do estoque** de materiais com base nos cronogramas dos pedidos realizados. Através de dashboards interativos, o usuário pode visualizar, planejar e analisar o impacto dos pedidos no estoque ao longo do tempo, facilitando a tomada de decisão e o planejamento da produção.

O sistema foi desenvolvido em Python utilizando o Streamlit, permitindo uma interface web intuitiva e visual.

## Funcionalidades principais

- Simulação dinâmica do estoque conforme datas de entrega e consumo dos pedidos
- Visualização de cronogramas (Gráfico de Gantt) para planejamento dos pedidos
- Filtros por material, cor, setor e pedidos específicos
- Relatórios e gráficos interativos para análise de consumo, cobertura e evolução do estoque
- Exportação dos dados para Excel

## Como acessar e usar

### 1. Executar localmente
1. Instale o [Python 3.10+](https://www.python.org/downloads/).
2. Instale o Streamlit:
	```bash
	pip install streamlit
	```
3. Clone este repositório:
	```bash
	git clone https://github.com/Natan-Ledur/Stock_app.git
	```
4. Execute o dashboard:
	```bash
	streamlit run maindash.py
	```
5. Acesse pelo navegador o endereço exibido (geralmente http://localhost:8501).

### 2. Gerar executável para Windows
Se quiser distribuir para usuários sem Python instalado:
1. Instale o PyInstaller:
	```bash
	pip install pyinstaller
	```
2. Gere o executável:
	```bash
	pyinstaller --onefile maindash.py
	```
3. O arquivo estará na pasta `dist/`.

### 3. Hospedar como aplicativo web
Você pode publicar o dashboard em plataformas como:
- [Streamlit Community Cloud](https://streamlit.io/cloud)
- Heroku
- AWS, Azure, etc.

Assim, qualquer usuário pode acessar via navegador, sem instalar nada.

## Alternativas de distribuição
- Compartilhe o link do repositório para que outros possam baixar e rodar localmente.
- Gere executáveis para facilitar o uso em Windows.
- Hospede online para acesso universal.

## Suporte
Para dúvidas ou sugestões, abra uma issue neste repositório.

## Como acessar e usar

### 1. Executar localmente
1. Instale o [Python 3.10+](https://www.python.org/downloads/).
2. Instale o Streamlit:
	```bash
	pip install streamlit
	```
3. Clone este repositório:
	```bash
	git clone https://github.com/Natan-Ledur/Stock_app.git
	```
4. Execute o dashboard:
	```bash
	streamlit run maindash.py
	```
5. Acesse pelo navegador o endereço exibido (geralmente http://localhost:8501).

### 2. Gerar executável para Windows
Se quiser distribuir para usuários sem Python instalado:
1. Instale o PyInstaller:
	```bash
	pip install pyinstaller
	```
2. Gere o executável:
	```bash
	pyinstaller --onefile maindash.py
	```
3. O arquivo estará na pasta `dist/`.

### 3. Hospedar como aplicativo web
Você pode publicar o dashboard em plataformas como:
- [Streamlit Community Cloud](https://streamlit.io/cloud)
- Heroku
- AWS, Azure, etc.

Assim, qualquer usuário pode acessar via navegador, sem instalar nada.

## Alternativas de distribuição
- Compartilhe o link do repositório para que outros possam baixar e rodar localmente.
- Gere executáveis para facilitar o uso em Windows.
- Hospede online para acesso universal.

## Suporte
Para dúvidas ou sugestões, abra uma issue neste repositório.
