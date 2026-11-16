ARG BUILD_FROM
FROM $BUILD_FROM

# L'agente usa solo la libreria standard di Python: nessuna dipendenza da scaricare.
# tzdata: i fusi orari, per mostrare le ore come in Home Assistant e non in UTC.
RUN apk add --no-cache python3 tzdata

WORKDIR /app
COPY agent ./agent

CMD ["python3", "-u", "-m", "agent.main"]
