ARG BUILD_FROM
FROM $BUILD_FROM

# L'agente usa solo la libreria standard di Python: nessuna dipendenza da scaricare.
RUN apk add --no-cache python3

WORKDIR /app
COPY agent ./agent

CMD ["python3", "-u", "-m", "agent.main"]
