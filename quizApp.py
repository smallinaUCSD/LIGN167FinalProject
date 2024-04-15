import os, random, glob, sys, re
import gradio as gr
import openai
from openai import OpenAI
import pandas as pd

#### API TOKEN
# initializing client
client = OpenAI(api_key="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")

#### LOADING LECTURES
"""
Extracting and formatting lecture title from filename
Assumes filename of the following structure:
{lecture_number}_{lecture_title}.txt
Example: 0_intro_to_lign101.txt
"""
def extract_lecture_title(file_name):
    try:
        parts = file_name.split('_')
        lecture_number = parts[0]
        lecture_title = ' '.join(parts[1:]).replace('.txt', '').capitalize()
        return f"Lecture {lecture_number}: {lecture_title}"
    except Exception as e:
        print(f"Error processing file name '{file_name}': {e}")
        return None
    
"""
Extracts all files ending in '.txt' from folder path
Assumes files of interest end in 'txt'
Sorts them numerically, assuming lecture number is delimited by '_' to start the
file name for each .txt file
"""
def list_lecture_files(folder_path):
    files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]
    files.sort(key=lambda x: int(x.split('_')[0]))
    return files
"""
Grabs first n lines of podcast lecture and returns as combined string.
We use this to pass into GPT for prompting and assume that the speaker
goes over a roadmap for the lecture at the beginning of the transcript, which is
true in the case of LIGN 101
This does not seem to work well with GPT 3.5, but works as intended for GPT 4
"""
def get_context(lecture, n):
    try:
        lecture = lecture_legend[lecture]
        file = glob.glob(os.path.join(folder_path, f'*{lecture}*'))
        if len(file) > 1:
            print(f"WARNING: This should have length 1 {file}")
            file = random.choice(file)
        else:
            file = file[0]
        
        context = ''
        with open(file, 'r') as r:
            for i, line in enumerate(r):
                line = line.strip('\n')
                context += line
                if i > n:
                    return context
        return context
    except Exception as e:
        print(f'Error reading lecture {lecture}', e)
        return None
    
"""
Parses lecture and grabs random n line chunk from the lecture, Use this to
pass into GPT for prompting as context. This is an adaptation of get_context to
work better with GPT 3.5
"""
def get_context_gpt3(lecture, n):
    try:
        lecture = lecture_legend[lecture]
        file = glob.glob(os.path.join(folder_path, f'*{lecture}*'))
        if len(file) > 1:
            print(f"WARNING: This should have length 1 {file}")
            file = random.choice(file)
        else:
            file = file[0]
        with open(file, 'r') as r:
            file_length = len(r.readlines())
        start_line = random.randint(0, file_length-n-1)
        context = ''
        with open(file, 'r') as r:
            for i, line in enumerate(r):
                if i < start_line:
                    continue
                elif i > start_line + n - 1:
                    return context
                else:
                    line = line.strip('\n')
                    context += line + ' '
        return context
    except Exception as e:
        print(f'Error reading lecture {lecture}', e)
        return None

# Assuming folder titled 'podcast_transcripts' in the same directory as this py file
py_path = os.path.dirname(os.path.abspath(__file__))
folder_path = os.path.join(py_path, 'podcast_transcripts')
# folder_path = PLACEHOLDER ## Uncomment line and replace placeholder with path
if not os.path.exists(folder_path) or os.listdir(folder_path) == 0:
    try:
        del(py_path)
        sys.exit(1)
    except SystemExit:
        print(f'folder_path = {folder_path}\n Does not exist or is empty. Please manually set the path where the desired podcast transcripts are on your local system on line 13 of quizApp.py')
lecture_files = list_lecture_files(folder_path)        
lecture_titles = [extract_lecture_title(file) for file in lecture_files if extract_lecture_title(file) is not None]
lecture_legend = {extract_lecture_title(file) : file for file in lecture_files}
del(lecture_files)


#### QUIZ APP CLASS
class QuizApp:
    def __init__(self, lectures, question_count, difficulty):
        self.lecture_titles = lectures  
        self.question_count = int(question_count)
        self.difficulty = difficulty
        self.current_difficulty = difficulty
        self.current_question_index = 0
        self.score = 0
        self.current_question_score = None
        self.gpt_response = None
        self.current_question_type = None
        self.current_lecture = None
        self.current_context = None
        self.full_response = None

        # self.full_generated_text = None
        self.score_data = {'question_number': [], 
                           'score': [],
                           'question_type': [],
                           'difficulty': [],
                           'lecture': []
                           }
        
    def new_question(self):
        self.gpt_response = None
        self.current_question_type = None
        self.current_lecture = None
        self.current_question_index += 1
        self.current_context = None
        self.full_response = None
        # self.full_generated_text = None

    def update_score_data(self):
        self.score_data['question_number'].append(self.current_question_index)
        self.score_data['score'].append(self.current_question_score)
        self.score_data['question_type'].append(self.current_question_type)
        self.score_data['difficulty'].append(self.current_difficulty)
        self.score_data['lecture'].append(self.current_lecture)

    def check_answer(self, user_answer):
        try:
            question_part = self.gpt_response['question_text']
            answer_part = self.gpt_response['answer_text']
            self.current_question_score = None
            if self.current_question_type == 'multiple-choice':
                user_answer = user_answer.strip().upper()
                correct_answer = answer_part.strip().upper()[0]
                letters = ['A', 'B', 'C', 'D']
                patterns = ['', '.', ')', '.)']
                valid_answers = {f"{letter}{pattern}": letter for letter in letters for pattern in patterns}
                normalized_user_answer = valid_answers.get(user_answer, None)
                normalized_correct_answer = valid_answers.get(correct_answer)
                if normalized_user_answer is None:
                    feedback = f'Please enter one of {letters} to indicate your choice'
                elif normalized_correct_answer is None:
                    feedback = f'Error parsing correct answer {answer_part}'
                elif normalized_correct_answer == normalized_user_answer:
                    feedback = 'Correct answer!'
                    self.score += 1
                    self.current_question_score = 1
                else:
                    feedback = f'Incorrect.\nYour answer was: {user_answer}\nCorrect Answer is: {answer_part}'

            elif self.current_question_type == 'true/false':
                user_answer = user_answer.strip().lower()
                valid_answers = {'t': 'true', 'true': 'true', 'f': 'false', 'false': 'false'}
                normalized_user_answer = valid_answers.get(user_answer, None)
                correct_answer = re.search(r'\b(true|false)\b', answer_part.lower()).group()
                normalized_correct_answer = valid_answers.get(correct_answer, None)
                if normalized_user_answer is None:
                    feedback = "Invalid answer format. Please answer with 'True' or 'False'." 
                elif normalized_correct_answer is None:
                    feedback = f"Error parsing correct answer: {answer_part}"
                elif normalized_correct_answer == normalized_user_answer:
                    feedback = 'Correct answer!'
                    self.score += 1
                    self.current_question_score = 1    
                else:
                    feedback = f'Incorrect.\nYour answer was: {user_answer}\nCorrect Answer is: {answer_part}'
                    self.current_question_score = 0

            elif self.current_question_type == 'fill-in-the-blank':
                correct_answer = answer_part.split('\n')[0].strip().lower()
                user_answer = user_answer.lower().strip()
                if user_answer == correct_answer:
                    feedback = 'Correct answer!'
                    self.score += 1
                    self.current_question_score = 1
                else:
                    feedback = f'Incorrect.\nYour answer was: {user_answer}\nCorrect answer is: {answer_part}\nValidating is finnicky, so give yourself an imaginary point if you think you had a correct answer'
                    self.current_question_score = 0
            else:
                feedback = 'Error: unrecognized question type'

            if self.current_question_score is not None:
                self.update_score_data()
            return feedback
        
        except Exception as e:
            feedback = f"Error: {e}"
            return feedback
        

    def generate_question(self):
        self.new_question()
        self.current_lecture = random.choice(self.lecture_titles)
        self.current_question_type = random.choice(['multiple-choice', 'true/false', 'fill-in-the-blank'])
        # self.current_question_type = 'true/false'
        lecture_context = get_context_gpt3(self.current_lecture, 30)
        textbook = 'An Introduction to Language by Fromkin, Rodman and Hyams'

        if self.difficulty != 'Adaptive':
            self.current_difficulty = self.difficulty
        else:
            if len(self.score_data['score']) < 3:
                self.current_difficulty = 'Medium'
            else:
                recent_score = 0
                last_score_index = len(self.score_data['score']) - 1
                for i in range(last_score_index, last_score_index-3, -1):
                    print(i)
                    recent_score += self.score_data['score'][i]
                if recent_score == 3 and self.current_difficulty == 'Medium':
                    self.current_difficulty = 'Hard'
                elif recent_score == 3 and self.current_difficulty == 'Easy':
                    self.current_difficulty = 'Medium'
                elif recent_score < 2 and self.current_difficulty == 'Hard':
                    self.current_difficulty = 'Medium'
                elif recent_score < 2 and self.current_difficulty == 'Medium':
                    self.current_difficulty = 'Easy'
        

        # Consistency for mcq
        question_type = self.current_question_type
        if question_type == 'multiple-choice':
            question_type += ' (A., B., C., or D.)'        
        prompt = (f'"""{lecture_context}"""\n'
                    f'Above is a brief excerpt of a college level lecture on Linguistics. The title of the lecture is titled {self.current_lecture} based on the textbook {textbook}. Write a {self.current_difficulty} difficulty {question_type} question that covers a topic from the excerpt based on the textbook to promote student understanding and learning. The except and lecture title will not be provided with the question. On a new line indicated by "Correct Answer:", provide the correct answer and an explanation as to why it is correct.')
        try:
            chat_completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": prompt}]
            )
            
            response_text = chat_completion.choices[0].message.content.strip()
            print("Prompt:", prompt)
            print("API response:", response_text)

            response_text = chat_completion.choices[0].message.content.strip()
            if "Correct Answer:" in response_text:
                question_part, answer_part = response_text.split("Correct Answer:")
                self.gpt_response = {
                    "question_type": self.current_question_type,
                    "question_text": question_part.strip(),
                    "answer_text": answer_part.strip()
                }
                # self.full_generated_text =f" {self.gpt_response['question_type']}|{self.gpt_response['question_text']}|{self.gpt_response['answer_text']}"
                self.current_context = lecture_context
                self.full_response = response_text

            else:
                self.gpt_response = {"error": "Failed to generate correctly formatted question."}

        except openai.BadRequestError as e:
            print(f'Error: {e}')
            print(prompt)
            self.gpt_response = {"error": "BadRequestError"}
        except openai.APIConnectionError as e:
            print("The server could not be reached")
            print(e.__cause__)  # Underlying Exception
            self.gpt_response = {"error": "Error: The server could not be reached."}
        except openai.RateLimitError as e:
            print("A 429 status code was received; we should back off a bit.")
            self.gpt_response = {"error": f"Error: Rate limit exceeded. Please try again later. {e}"}
        except openai.APIStatusError as e:
            print("A non-200-range status code was received")
            print(e.status_code)
            print(e.response)
            self.gpt_response = {"error": f"Error: API status error with status code {e.status_code}."}
        except Exception as e:
            print(f"General error in generating question: {e}")
            self.gpt_response = {"error": "Error in generating question."}        

    def revise_question(self, feedback):
        context = self.current_context
        original_question = self.full_response
        new_prompt = (
            f'"""{context}"""\n'
            f'Above is an excerpt from a college Linguistics lecture titled {self.current_lecture}. Based on the following feedback, modify the question:\n\n'
            f'Original Question: {original_question}\n'
            f'Feedback: {feedback}\n\n'
            'Regenerate the question with necesary adjustments, and provide the correct answer with explanation in the same format as the original question.'
        )
        try:
            chat_completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": new_prompt}]
            )

            response_text = chat_completion.choices[0].message.content.strip()
            print("API response:", response_text)
            self.original_question = response_text
            if "Correct Answer:" in response_text:
                question_part, answer_part = response_text.split("Correct Answer:")
                self.gpt_response = {
                    "question_type": self.current_question_type,
                    "question_text": question_part.strip(),
                    "answer_text": answer_part.strip()
                }
            else:
                self.gpt_response = {"error": "Failed to generate correctly formatted question."} 

        except openai.BadRequestError as e:
            print(f'Error: {e}')
            print(new_prompt)
            self.gpt_response = {"error": "BadRequestError"}
        except openai.APIConnectionError as e:
            print("The server could not be reached")
            print(e.__cause__)  # Underlying Exception
            self.gpt_response = {"error": "Error: The server could not be reached."}
        except openai.RateLimitError as e:
            print("A 429 status code was received; we should back off a bit.")
            self.gpt_response = {"error": f"Error: Rate limit exceeded. Please try again later. {e}"}
        except openai.APIStatusError as e:
            print("A non-200-range status code was received")
            print(e.status_code)
            print(e.response)
            self.gpt_response = {"error": f"Error: API status error with status code {e.status_code}."}
        except Exception as e:
            print(f"General error in generating question: {e}")
            self.gpt_response = {"error": "Error in generating question."}


    def reset_quiz(self):
        self.lecture_titles = []
        self.question_count = 0
        self.difficulty = None
        self.current_difficulty = None
        self.current_question_index = 0
        self.score = 0
        self.gpt_response = None
        self.current_question_type = None
        self.current_lecture = None
        # self.full_generated_text = None
        self.score_data = {'question_number': [], 
                           'score': [],
                           'question_type': [],
                           'difficulty': [],
                           'lecture': []
                           }

def validate_and_start_quiz(lectures, question_count, difficulty):
    if not lectures:
        question_msg = "Please select at least one lecture"
        feedback_msg = ""
        enable_start = True
        enable_next_submit = False
    elif question_count is None or question_count == [] or question_count == 0:
        question_msg = "Please select the number of questions."
        feedback_msg = ""
        enable_start = True
        enable_next_submit = False
    elif difficulty is None:
        question_msg = "Please select the question difficulty."
        feedback_msg = ""
        enable_start = True
        enable_next_submit = False
    else:
        global quiz 
        quiz = QuizApp(lectures, question_count, difficulty)
        question_msg, feedback_msg, _placeholder, _placeholder2 = next_question()
        enable_start = False
        enable_next_submit = True
    return question_msg, feedback_msg, gr.update(interactive=enable_next_submit), gr.update(interactive=enable_next_submit), gr.update(interactive=enable_start)


def submit_answer(user_answer):
    feedback_msg = quiz.check_answer(user_answer)
    # print(quiz.current_question_score)
    if quiz.current_question_score is not None:
        return feedback_msg, gr.update(interactive=False)
    else:
        return feedback_msg, gr.update(interactive=True)
    
score_df = pd.DataFrame()
def next_question():
    if quiz is None:
        question_msg = "Quiz is not initialized. Please click 'Start Quiz'"
        feedback_msg = ""
    elif quiz.current_question_index >= quiz.question_count:
        question_msg = "Quiz Complete!"
        if quiz.question_count != 0:
            feedback_msg = f"Your score is {quiz.score} / {quiz.question_count} ({(quiz.score / quiz.question_count)*100:.2f}%)"
            global score_df
            if len(score_df) != 0:
                df = pd.DataFrame.from_dict(quiz.score_data)
                quiznum = score_df.quiz_num.unique()[-1] + 1
                df['quiz_num'] = quiznum
                score_df = pd.concat([score_df, df])
            else:
                df = pd.DataFrame.from_dict(quiz.score_data)
                df['quiz_num'] = 1
                score_df = df
            reset()
        else:
            feedback_msg = "Looks like there were 0 valid questions. Sorry about that! Please click 'Start Quiz' again to get a new quiz going."
    else:
        quiz.generate_question()
        if "error" in quiz.gpt_response:
            question_msg = f"Failed to generate a properly formatted question, please click 'Next Question'\n{quiz.gpt_response['error']}"
            quiz.question_count -= 1
            feedback_msg = ""
        else:
            question_msg = quiz.gpt_response['question_text']
            feedback_msg = ""
    clear_user_input = ""
    return question_msg, feedback_msg, gr.update(interactive=True), clear_user_input


def reset():
    global quiz
    quiz = None
    question_msg = ""
    feedback_msg = ""
    return question_msg, feedback_msg, gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=False)

def update_plot():
    df = score_df  
    # Score Over Time
    sot = gr.LinePlot()
    if not df.empty:
        score_over_time_data = df.groupby('quiz_num')['score'].mean().reset_index()
        sot = gr.LinePlot(score_over_time_data, x='quiz_num', y='score', label='Average Score')
    # Performance by Difficulty
    dp = gr.BarPlot()
    if not df.empty:
        difficulty_performance = df.groupby('difficulty')['score'].mean().reset_index()
        dp = gr.BarPlot(difficulty_performance, x='difficulty', y='score', label='Average Score')
    # Question Type Performance
    qp = gr.BarPlot()
    if not df.empty:
        question_type_performance = df.groupby('question_type')['score'].mean().reset_index()
        qp = gr.BarPlot(question_type_performance, x='question_type', y='score', label='Average Score')
    # Average Score per Lecture
    lp = gr.BarPlot()
    if not df.empty:
        lecture_performance = df.groupby('lecture')['score'].mean().reset_index()
        lp = gr.BarPlot(lecture_performance, x='lecture', y='score', label='Average Score')
    return sot, dp, qp, lp
    
#### INSTRUCTOR VERSION
def instructor_gen_question(lectures):
    if not lectures:
        display_text = "Please select at least one lecture"
        return display_text, gr.update(interactive=False), gr.update(interactive=False)
    else:
        global instructor_quiz 
        instructor_quiz = QuizApp(lectures, 1, 'Medium')
        instructor_quiz.generate_question()
        display_text = (f"Question: {instructor_quiz.gpt_response['question_text']}\n"
                        f"Correct Answer: {instructor_quiz.gpt_response['answer_text']}"
                )   
    return display_text, gr.update(interactive=True), gr.update(interactive=True)

question_list = None
def instructor_accept_question(question, lectures):
    global question_list
    if question_list is None:
        question_list = []
    question_list.append(question)
    new_question, _placeholder, _placeholder2= instructor_gen_question(lectures)
    feedback_msg = 'Saved Question and Answer! Output your saved questions to a file with "Finish Question Generation" if you are done.'
    return new_question, feedback_msg, gr.update(interactive=True)
    
def instructor_reject_and_regen(feedback):
    instructor_quiz.revise_question(feedback)
    if 'error' in instructor_quiz.gpt_response:
        status_msg = 'Potentially failed to generate properly formatted question, click "Generate Question" to change questions if necessary'
        question_msg = instructor_quiz.full_response
    else:
        status_msg = 'Successfully regenerated question'
        question_msg = (f"Question: {instructor_quiz.gpt_response['question_text']}\n"
                        f"Correct Answer: {instructor_quiz.gpt_response['answer_text']}")
    clear_feedback_tbox = ""
    return question_msg, status_msg, clear_feedback_tbox

def save_questions():
    clear_feedback_tbox = ""
    clear_question_tbox = ""
    if question_list is None:
        status_msg = 'Saved Question List is empty'
    else:
        try:
            output_file = os.path.join(py_path, 'accepted_questions')
            new_path = output_file+'.txt'
            i = 0
            while os.path.exists(new_path):
                i += 1
                new_path = f'{output_file}{i}.txt'
            with open(new_path, 'w') as w:
                for i, q in enumerate(question_list):
                    w.write(f'Question {i+1}:\n')
                    w.write(f'{q}\n\n\n')
            status_msg = f'Saved {len(question_list)} question(s) to:\n{new_path}'
        except Exception as e:
            status_msg = f'Error Saving Questions: {e}'
        return status_msg, gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False), clear_feedback_tbox, clear_question_tbox
    return status_msg, gr.update(interactive=True), gr.update(interactive=True), gr.update(interactive=True), clear_feedback_tbox, clear_question_tbox



#### USER INTERFACE - Gradio
with gr.Blocks(theme='JohnSmith9982/small_and_pretty') as demo:
    with gr.Tab('Student Quiz App'):
        gr.Markdown("<h1 style='text-align: center;'><u>LIGN 101 Practice Quiz</u></h1>")
        with gr.Row():
            lecture_selection = gr.CheckboxGroup(choices=lecture_titles, label="Select Lectures")
        with gr.Row():
            question_count_dropdown = gr.Dropdown(choices=[1, 5, 10, 15, 20], label="Select the number of questions")
            question_difficulty = gr.Radio(choices=['Easy', 'Medium', 'Hard', 'Adaptive'], label='Question Difficulty')
        with gr.Row():    
            start_button = gr.Button("Start Quiz")
        with gr.Row():
            question_display = gr.Textbox(label="Question", interactive=False)
        with gr.Row():    
            user_answer_input = gr.Textbox(label="Your Answer")
        with gr.Row():    
            submit_button = gr.Button("Submit Answer", interactive=False)
            next_question_button = gr.Button("Next Question", interactive=False) 
        feedback_display = gr.Textbox(label="Feedback", interactive=False)
        with gr.Row():
            reset_button = gr.Button("Reset Quiz")
        with gr.Row():
            with gr.Column(scale=0):
                update_plots = gr.Button("Update Performance Plots")
            with gr.Column(scale=2):       
                with gr.Tabs():
                    with gr.TabItem("Score Over Time"):
                        score_over_time = gr.LinePlot()
                    with gr.TabItem("Performance by Difficulty"):
                        difficulty_perf = gr.BarPlot()
                    with gr.TabItem("Question Type Performance"):
                        question_type_perf = gr.BarPlot()
                    with gr.TabItem("Average Score per Lecture"):
                        lecture_perf = gr.BarPlot()
            

        start_button.click(
            validate_and_start_quiz,
            inputs=[lecture_selection, question_count_dropdown, question_difficulty],
            outputs=[question_display, feedback_display, submit_button, next_question_button,start_button]
        )

        submit_button.click(
            submit_answer,
            inputs=[user_answer_input],
            outputs = [feedback_display, submit_button]
        )

        next_question_button.click(
            next_question,
            outputs=[question_display, feedback_display, submit_button, user_answer_input]
        )
        reset_button.click(
            reset,
            outputs=[question_display, feedback_display, start_button, submit_button, next_question_button]
        )

        update_plots.click(
            update_plot,
            outputs=[score_over_time, difficulty_perf, question_type_perf, lecture_perf]
        )


    with gr.Tab('Instructor Quiz App'):
        gr.Markdown("<h1 style='text-align: center;'><u>Instructor Interface</u></h1>")
        with gr.Row():
            instructor_lecture_selection = gr.CheckboxGroup(choices=lecture_titles, label="Select Lectures for Question Generation")
            
        generate_question_button = gr.Button("Generate Question")

        instructor_question_display = gr.Textbox(label="Generated Question", interactive=False)
        instructor_feedback_input = gr.Textbox(label="Feedback")
        with gr.Row():
            accept_question_button = gr.Button("Accept Question", interactive=False)
            reject_and_regenerate_button = gr.Button("Reject and Regenerate with Feedback", interactive=False)
        finish_button = gr.Button("Finish Question Generation", interactive=False)
        instructor_feedback_display = gr.Textbox(label="Status", interactive=False)

        generate_question_button.click(
            instructor_gen_question,
            inputs = [instructor_lecture_selection],
            outputs = [instructor_question_display, accept_question_button, reject_and_regenerate_button]
        )

        accept_question_button.click(
            instructor_accept_question,
            inputs=[instructor_question_display, instructor_lecture_selection],
            outputs=[instructor_question_display, instructor_feedback_display, finish_button]
        )

        reject_and_regenerate_button.click(
            instructor_reject_and_regen,
            inputs=[instructor_feedback_input],
            outputs=[instructor_question_display, instructor_feedback_display, instructor_feedback_input]
        )


        finish_button.click(
            save_questions,
            outputs=[instructor_feedback_display, accept_question_button, reject_and_regenerate_button, finish_button, instructor_feedback_input, instructor_question_display]
        )

demo.launch(share=True)
