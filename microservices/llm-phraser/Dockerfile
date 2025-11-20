# Purpose: Defines the steps to build a production-ready container image
# for the llm-phraser service.

# --- Stage 1: The "Builder" Stage ---
FROM python:3.11-slim as builder

# Create a virtual environment
RUN python -m venv /opt/venv
# Activate the venv for subsequent RUN commands
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies *into the venv*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN pip install gunicorn

# --- Stage 2: The "Final" Stage ---
FROM python:3.11-slim

# Set a new working directory. This will be the PARENT of our 'app' package.
WORKDIR /service

# Copy the *entire virtual environment* from the 'builder' stage
COPY --from=builder /opt/venv /opt/venv

# Copy our application source code into a SUB-DIRECTORY named 'app'
COPY ./app /service/app

# Expose the port our application will run on
EXPOSE 8000

# Tell the container to use the executables from our venv
ENV PATH="/opt/venv/bin:$PATH"

# Define the command to run our application
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]