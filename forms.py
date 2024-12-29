from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length

class FeedbackForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    feedback_type = SelectField('Feedback Type', 
        choices=[
            ('bug', 'Bug Report'),
            ('feature', 'Feature Request'),
            ('general', 'General Feedback')
        ],
        validators=[DataRequired()]
    )
    message = TextAreaField('Message', 
        validators=[DataRequired(), Length(min=10, max=1000)]
    )
    submit = SubmitField('Submit Feedback') 