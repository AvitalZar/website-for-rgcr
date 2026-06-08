from flask import Flask, render_template, request
from pref_voting.stochastic_methods import RGCR
from pref_voting.grade_profiles import GradeProfile
import io
import logging

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

# 3. Results Page Route (Handles the form submission)
@app.route('/results', methods=['POST'])
def results():
    num_reviewers = int(request.form.get('num_reviewers'))
    num_items = int(request.form.get('num_items'))
    max_score = int(request.form.get('max_score', 10))

    reviewers_list = []

    for r in range(1, num_reviewers + 1):
        reviewer_dict = {}
        
        for i in range(1, num_items + 1):
            is_active = request.form.get(f'active_r{r}_i{i}') == 'on'
            
            if is_active:
                score = int(request.form.get(f'score_r{r}_i{i}'))
                reviewer_dict[i] = score
        
        reviewers_list.append(reviewer_dict)


    results = None
    function_logs = ""
    error_message = None

    log_capture_string = io.StringIO()
    ch = logging.StreamHandler(log_capture_string)
    ch.setLevel(logging.DEBUG)
    logger = logging.getLogger('RGCR')
    if not logger:
        raise "logger not found"
    logger.setLevel(logging.DEBUG)
    logger.addHandler(ch)

    try:
        results = compute_rgcr(reviewers_list, max_score)
    except Exception as e:
        error_message = str(e)
    finally:
        logger.removeHandler(ch)
        function_logs = log_capture_string.getvalue()

    avg_result = mean_estimator(reviewers_list, max_score)

    return render_template('results.html', 
                        result_ranking = results,
                            avg_ranking = avg_result,
                        logs=function_logs,
                        error_message=error_message,
                        reviewers_list=reviewers_list)

# 4. About Page Route
@app.route('/about')
def about_page():
    return render_template('about.html')


def compute_rgcr(reviewers_list, max_score):
    scores = range(max_score + 1)
    grade_profile = GradeProfile(reviewers_list, scores)
    return RGCR(grade_profile)

def mean_estimator(reviewers_list, max_score):
    scores = range(max_score + 1)
    gprofile = GradeProfile(reviewers_list, scores)
    return sorted(gprofile.candidates, key=lambda c: gprofile.avg(c) if gprofile.has_grade(c) else 0, reverse=True)




if __name__ == '__main__':
    app.run(debug=True, port=5000)