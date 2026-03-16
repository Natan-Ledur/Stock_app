# Dockerfile para rodar o app Streamlit
FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && \
	apt-get install -y build-essential unixodbc unixodbc-dev && \
	rm -rf /var/lib/apt/lists/*

# Copia os arquivos do projeto
COPY . /app

# Instala as dependências do Python
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expõe a porta padrão do Streamlit
EXPOSE 8882

# Comando para iniciar o Streamlit
CMD ["streamlit", "run", "app/maindash.py", "--server.address=0.0.0.0", "--server.port=8882"]
