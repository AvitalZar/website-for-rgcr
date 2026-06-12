from flask import Flask, render_template, request, Response
from rgcr_lite.rgcr_methods import RGCR, rgcr_from_csv
import io
import logging
import os
import tempfile
from werkzeug.utils import secure_filename

# Initialize the Flask application
app = Flask(__name__)

# 1. Home Page Route
@app.route('/')
def index():
    return render_template('index.html')

# 2. Input Page Route
@app.route('/input')
def input_page():
    return render_template('input.html')

# 3. Results Page Route (Handles the form submission and CSV upload)
@app.route('/results', methods=['POST'])
def results():
    results = None
    function_logs = ""
    error_message = None
    reviewers_list = []
    avg_result = []

    # Setup logger
    log_capture_string = io.StringIO()
    ch = logging.StreamHandler(log_capture_string)
    ch.setLevel(logging.DEBUG)
    logger = logging.getLogger('RGCR')
    
    if not logger:
        raise Exception("logger not found")
        
    logger.setLevel(logging.DEBUG)
    logger.addHandler(ch)

    try:
        # Check if a CSV file was uploaded
        if 'csv_file' in request.files and request.files['csv_file'].filename != '':
            csv_file = request.files['csv_file']
            
            # Create a temporary path to save the uploaded file
            temp_dir = tempfile.gettempdir()
            filename = secure_filename(csv_file.filename)
            temp_path = os.path.join(temp_dir, filename)
            
            csv_file.save(temp_path)
            
            try:
                # Execute directly from the temporary CSV file path
                results = rgcr_from_csv(temp_path)
            except Exception as e:
                error_message = str(e)
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        else:
            # Standard manual form processing
            num_reviewers_str = request.form.get('num_reviewers')
            
            # Ensure standard form inputs exist before parsing
            if num_reviewers_str:
                num_reviewers = int(num_reviewers_str)
                num_items = int(request.form.get('num_items'))
                max_score = int(request.form.get('max_score', 10))

                for r in range(1, num_reviewers + 1):
                    reviewer_dict = {}
                    for i in range(1, num_items + 1):
                        is_active = request.form.get(f'active_r{r}_i{i}') == 'on'
                        if is_active:
                            score = int(request.form.get(f'score_r{r}_i{i}'))
                            reviewer_dict[i] = score
                    
                    reviewers_list.append(reviewer_dict)

                try:
                    # Execute standard RGCR process
                    results = RGCR(reviewers_list, max_score)
                except Exception as e:
                    error_message = str(e)
                
                # Calculate average result independently, mirroring the original code structure
                avg_result = mean_estimator(reviewers_list, max_score)

    finally:
        logger.removeHandler(ch)
        function_logs = log_capture_string.getvalue()

    return render_template('results.html', 
                           result_ranking=results,
                           avg_ranking=avg_result,
                           logs=function_logs,
                           error_message=error_message,
                           reviewers_list=reviewers_list)

# 4. About Page Route
@app.route('/about')
def about_page():
    return render_template('about.html')

def mean_estimator(reviewers_list, max_score):
    items = range(max_score+1)
    keys = {k for d in reviewers_list for k in d}
    grouped = {k: [d[k] for d in reviewers_list if k in d] for k in keys}
    ranking = sorted(grouped, key=lambda k: sum(grouped[k]) / len(grouped[k]), reverse=True)

    ranking_set = set(ranking)
    ranking += [item for item in items if item not in ranking_set]
    return ranking

# Route to handle CSV download
@app.route('/download_csv', methods=['POST'])
def download_csv():
    # Retrieve the comma-separated results string from the form
    results_str = request.form.get('results_data', '')
    
    # Create and return a CSV file response
    return Response(
        results_str,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=results.csv"}
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)