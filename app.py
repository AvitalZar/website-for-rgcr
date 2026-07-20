from flask import Flask, render_template, request, Response
from rgcr_lite import RGCR, voters_from_csv
import io
import json
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
@app.route('/input', methods=['GET', 'POST'])
def input_page():
    prefill = None
    csv_error = None
 
    if request.method == 'POST':
        try:
            reviewers_json = request.form.get('prefill_reviewers', '[]')
            raw_reviewers = json.loads(reviewers_json)
            # JSON object keys are always strings - convert item ids back to int if needed
            try:
                reviewers_list = [
                    {int(item_id): score for item_id, score in reviewer.items()}
                    for reviewer in raw_reviewers
                ]
            except ValueError:
                reviewers_list = raw_reviewers  # Keep as is if conversion fails

            num_items = int(request.form.get('prefill_num_items', 0))
            max_score = int(request.form.get('prefill_max_score', 100))
            item_names_json = request.form.get('prefill_item_names', '[]')
 
            prefill = {
                'num_reviewers': len(reviewers_list),
                'num_items': num_items,
                'max_score': max_score,
                'reviewers': reviewers_list,
                'item_names': json.loads(item_names_json)
            }
        except (ValueError, TypeError, json.JSONDecodeError):
            # If anything about the submitted prefill data is malformed,
            # just fall back to a blank input page rather than erroring out.
            prefill = None
            csv_error = "Could not restore your previous input. Please re-enter it."
 
    return render_template('input.html', prefill=prefill, csv_error=csv_error)

@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    csv_error = None
    prefill = None
 
    csv_file = request.files.get('csv_file')
    if not csv_file or csv_file.filename == '':
        csv_error = "No CSV file was uploaded."
        return render_template('input.html', prefill=None, csv_error=csv_error)
 
    temp_dir = tempfile.gettempdir()
    filename = secure_filename(csv_file.filename)
    temp_path = os.path.join(temp_dir, filename)
    csv_file.save(temp_path)
 
    try:
        reviewers_list = voters_from_csv(temp_path)
        # Create a dictionary to remove duplicates while preserving insertion order, then convert to list
        unique_items = list(dict.fromkeys(item_id for reviewer in reviewers_list for item_id in reviewer))
        '''
        item_to_id = {item_id: idx for idx, item_id in enumerate(unique_items)}
        reviewers_list = [
            {item_to_id[item_id]: score for item_id, score in reviewer.items()}
            for reviewer in pre_reviewers_list
        ]'''


        max_score = max(score for reviewer in reviewers_list for score in reviewer.values()) if reviewers_list else 100
        num_items = len(unique_items)
        prefill = {
            'num_reviewers': len(reviewers_list),
            'num_items': num_items,
            'max_score': max_score,
            'reviewers': reviewers_list,
            'item_names': list(unique_items)
        }
    except Exception as e:
        csv_error = f"Could not read the CSV file: {e}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
 
    return render_template('input.html', prefill=prefill, csv_error=csv_error)

# 3. Results Page Route (Handles the form submission)
@app.route('/results', methods=['POST'])
def results():
    results = None
    function_logs = ""
    error_message = None
    reviewers_list = []
    avg_result = []
    item_names = []
    num_items = 0
    max_score = 100
 
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
        # Standard manual form processing (this now also covers data that
        # originated from a CSV upload or from returning from the results page,
        # since both are prefilled into this same form before submission).
        num_reviewers_str = request.form.get('num_reviewers')
 
        if num_reviewers_str:
            num_reviewers = int(num_reviewers_str)
            num_items = int(request.form.get('num_items'))
            max_score = int(request.form.get('max_score', 100))

            for key in request.form.keys():
                if key.startswith("active_r"):
                    # Split the key 'active_r1_Apple' into ['active', 'r1', 'Apple']
                    parts = key.split('_', 2)
                    if len(parts) == 3:
                        raw_item_name = parts[2]
                        
                        # Convert to int if possible, otherwise keep as string
                        try:
                            parsed_item = int(raw_item_name)
                        except ValueError:
                            parsed_item = raw_item_name
                            
                        # Add to item_names list while maintaining insertion order
                        if parsed_item not in item_names:
                            item_names.append(parsed_item)
 
            for r in range(1, num_reviewers + 1):
                reviewer_dict = {}
                for item in item_names:
                    is_active = request.form.get(f'active_r{r}_{item}') == 'on'
                    if is_active:
                        score = int(request.form.get(f'score_r{r}_{item}'))
                        reviewer_dict[item] = score
 
                reviewers_list.append(reviewer_dict)
 
            try:
                # Execute standard RGCR process
                results = rgcr_estimator(reviewers_list, item_names)
            except Exception as e:
                error_message = str(e)
 
            # Calculate average result independently, mirroring the original code structure
            avg_result = mean_estimator(reviewers_list, item_names)
 
    finally:
        logger.removeHandler(ch)
        function_logs = log_capture_string.getvalue()
 
    return render_template('results.html',
                           result_ranking=results,
                           avg_ranking=avg_result,
                           logs=function_logs,
                           error_message=error_message,
                           reviewers_list=reviewers_list,
                           num_items=num_items,
                           max_score=max_score,
                           item_names=item_names)

# 4. About Page Route
@app.route('/about')
def about_page():
    return render_template('about.html')

def mean_estimator(reviewers_list, items):
    keys = {k for d in reviewers_list for k in d}
    grouped = {k: [d[k] for d in reviewers_list if k in d] for k in keys}
    ranking = sorted(grouped, key=lambda k: sum(grouped[k]) / len(grouped[k]), reverse=True)

    ranking_set = set(ranking)
    ranking += [item for item in items if item not in ranking_set]
    return ranking

def rgcr_estimator(reviewers_list, items):
    ranking = RGCR(reviewers_list)
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