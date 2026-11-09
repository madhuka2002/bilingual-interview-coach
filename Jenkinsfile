pipeline {
    agent {
        label 'bic-python312-uv'
    }

    options {
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
    }

    environment {
        UV_NO_PROGRESS = '1'
        UV_PYTHON = '3.12'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git rev-parse HEAD'
            }
        }

        stage('Install locked dependencies') {
            steps {
                sh 'uv sync --locked'
            }
        }

        stage('Ruff') {
            steps {
                sh 'uv run ruff check .'
                sh 'uv run ruff format --check .'
            }
        }

        stage('Pytest') {
            steps {
                sh 'mkdir -p reports && rm -f reports/pytest.xml'
                sh 'uv run pytest --junitxml=reports/pytest.xml'
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'reports/pytest.xml'
                }
            }
        }

        stage('Dependency audit') {
            steps {
                sh 'uv audit --locked'
            }
        }
    }
}
