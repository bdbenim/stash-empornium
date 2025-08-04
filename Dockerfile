# this dockerfile is used to build the image for the emp_stash_fill service, install all the dependencies and run the service to listen to the tampermonkey script on the host browser

FROM python:3.12-slim

WORKDIR /emp_stash_fill

# Install system dependencies
RUN apt-get update && \
    apt-get install -y wget ffmpeg mediainfo build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/autobrr/mkbrr/releases/download/v1.14.0/mkbrr_1.14.0_linux_amd64.deb && \
    apt-get install -y ./mkbrr_1.14.0_linux_amd64.deb && \
    rm mkbrr_1.14.0_linux_amd64.deb

# Copy pyproject.toml and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy remaining files
COPY . .

# Remove build-essential as it is only needed during pip install
RUN apt-get remove -y build-essential

# Run the Flask app when the container is executed
ENTRYPOINT ["python", "emp_stash_fill.py", "--configdir", "/config"]
