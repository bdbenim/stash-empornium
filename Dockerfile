# this dockerfile is used to build the image for the emp_stash_fill service, install all the dependencies and run the service to listen on port 5000 and connect to the tampermonkey script on the host browser

FROM python:3.9-slim-buster

WORKDIR /emp_stash_fill

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg mktorrent && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install Python dependencies
COPY requirements.txt /emp_stash_fill//
RUN pip install --no-cache-dir -r requirements.txt

COPY . /emp_stash_fill/

# Expose the Flask port (change as needed)
EXPOSE 5000

# Run the Flask app when the container is executed
CMD ["python", "emp_stash_fill.py"]
