# this dockerfile is used to build the image for the emp_stash_fill service, install all the dependencies and run the service to listen to the tampermonkey script on the host browser

FROM python:3.12-slim

WORKDIR /emp_stash_fill

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg mktorrent mediainfo build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy remaining files
COPY . .

# Remove build-essential as it is only needed during pip install
RUN apt-get remove -y build-essential

# Run the Flask app when the container is executed
ENTRYPOINT ["python", "emp_stash_fill.py", "--configdir", "/config"]
